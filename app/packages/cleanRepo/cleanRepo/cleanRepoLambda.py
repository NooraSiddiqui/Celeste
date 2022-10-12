import json
import boto3
import cfnresponse

s3 = boto3.resource("s3")


def create(properties, physical_id):
    message = "Create Complete"
    print(message)
    return cfnresponse.SUCCESS, None


def update(properties, physical_id):
    return create(properties, physical_id)


def delete(properties, physical_id):
    region = properties["Region"]
    repository = properties["Repository"]
    removeRepository(repository)
    print("success")
    return cfnresponse.SUCCESS, physical_id


def removeRepository(ecr_repository):
    client = boto3.client("ecr")
    response = client.delete_repository(repositoryName=ecr_repository, force=True)


def handler(event, context):
    print("Received event: %s" % json.dumps(event))

    status = cfnresponse.FAILED
    new_physical_id = None

    try:
        properties = event.get("ResourceProperties")
        physical_id = event.get("PhysicalResourceId")

        status, new_physical_id = {
            "Create": create,
            "Update": update,
            "Delete": delete,
        }.get(event["RequestType"], lambda x, y: (cfnresponse.FAILED, None))(
            properties, physical_id
        )
    except Exception as e:
        print("Exception: %s" % e)
        status = cfnresponse.FAILED
    finally:
        cfnresponse.send(event, context, status, {}, new_physical_id)
