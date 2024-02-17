from pyflink.table import EnvironmentSettings, TableEnvironment
import os
import json

env_settings = EnvironmentSettings.in_streaming_mode()
table_env = TableEnvironment.create(env_settings)

statement_set = table_env.create_statement_set()

APPLICATION_PROPERTIES_FILE_PATH = "/etc/flink/application_properties.json"  # on kda

is_local = (
    True if os.environ.get("IS_LOCAL") else False
)  # set this env var in your local environment

if is_local:
    # only for local, overwrite variable to properties and pass in your jars delimited by a semicolon (;)
    APPLICATION_PROPERTIES_FILE_PATH = "application_properties.json"  # local

    CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
    table_env.get_config().get_configuration().set_string(
        "pipeline.jars",
        "file:///" + CURRENT_DIR + "/lib/flink-sql-connector-kinesis-1.15.2.jar",
    )


def get_application_properties():
    if os.path.isfile(APPLICATION_PROPERTIES_FILE_PATH):
        with open(APPLICATION_PROPERTIES_FILE_PATH, "r") as file:
            contents = file.read()
            properties = json.loads(contents)
            return properties
    else:
        print('A file at "{}" was not found'.format(APPLICATION_PROPERTIES_FILE_PATH))


def property_map(props, property_group_id):
    for prop in props:
        if prop["PropertyGroupId"] == property_group_id:
            return prop["PropertyMap"]


def create_source_views_table(table_name, stream_name, region, stream_initpos):
    return f"""CREATE TABLE {table_name} (
            event VARCHAR,
            messageid VARCHAR,
            userid VARCHAR,
            properties ROW<productid VARCHAR>
        ) 
        PARTITIONED BY (messageid)
        WITH (
            'connector' = 'kinesis',
            'stream' = '{stream_name}',
            'aws.region' = '{region}',
            'scan.stream.initpos' = '{stream_initpos}',
            'format' = 'json',
            'json.timestamp-format.standard' = 'ISO-8601'  
        )"""


def create_source_category_table(table_name, bucket_name):
    return f"""CREATE TABLE {table_name} (
            productid VARCHAR,
            categoryid VARCHAR
        )
        WITH (
            'connector' = 'filesystem',
            'format' = 'csv',
            'path' = '{bucket_name}'
        )"""


def create_sink_table(table_name, stream_name, region):
    return f""" CREATE TABLE {table_name} (
                event VARCHAR,
                messageid VARCHAR,
                userid VARCHAR,
                properties VARCHAR,
                categoryid VARCHAR
              )
              PARTITIONED BY (messageid)
              WITH (
                'connector' = 'kinesis',
                'stream' = '{stream_name}',
                'aws.region' = '{region}',
                'sink.partitioner-field-delimiter' = ';',
                'sink.batch.max-size' = '100',
                'format' = 'json',
                'json.timestamp-format.standard' = 'ISO-8601'
              ) """


def create_print_table(table_name):
    return f""" CREATE TABLE {table_name} (
                event VARCHAR,
                messageid VARCHAR,
                userid VARCHAR,
                properties VARCHAR,
                categoryid VARCHAR
              )
              WITH (
                'connector' = 'print'
              ) """


def main():
    # Application Property Keys
    input_property_group_key = "consumer.config.0"
    producer_property_group_key = "producer.config.0"
    source_csv_property_group_key = "source.config.0"

    input_stream_key = "input.stream.name"
    input_starting_position_key = "flink.stream.initpos"
    input_region_key = "aws.region"

    source_file_path = "file.path"

    output_stream_key = "output.stream.name"
    output_region_key = "aws.region"

    # tables
    input_table_name = "input_table"
    source_table_name = "category_table"
    output_table_name = "output_table"

    # get application properties
    props = get_application_properties()

    input_property_map = property_map(props, input_property_group_key)
    output_property_map = property_map(props, producer_property_group_key)
    source_property_map = property_map(props, source_csv_property_group_key)

    input_stream = input_property_map[input_stream_key]
    input_region = input_property_map[input_region_key]
    stream_initpos = input_property_map[input_starting_position_key]

    source_path = source_property_map[source_file_path]

    output_stream = output_property_map[output_stream_key]
    output_region = output_property_map[output_region_key]

    # 2. Creates a source table from a Kinesis Data Stream
    table_env.execute_sql(
        create_source_views_table(input_table_name, input_stream, input_region, stream_initpos)
    )

    # 3. Creates a source table from S3
    table_env.execute_sql(
        create_source_category_table(table_name=source_table_name, bucket_name=source_path)
    )

    # 4. Creates a sink table writing to a Kinesis Data Stream
    table_env.execute_sql(
       create_sink_table(output_table_name, output_stream, output_region)
    )

    # print
    #table_env.execute_sql(
    #    create_print_table(output_table_name)
    #)

    table_result = table_env.execute_sql("INSERT INTO {0} SELECT "
                                         "event,messageid,userid,properties.productid AS productid, ct.categoryid "
                                         "FROM input_table AS it JOIN category_table AS ct  ON "
                                         "it.properties.productid = ct.productid"
                                         .format(output_table_name))
    if is_local:
        table_result.wait()
    else:
        # get job status through TableResult
        print(table_result.get_job_client().get_job_status())


if __name__ == "__main__":
    main()
