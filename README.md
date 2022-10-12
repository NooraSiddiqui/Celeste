# CELESTE #
Celeste is a resilient, open-source cloud architecture for implementing genomics workflows that has successfully analyzed petabytes of participant genomic information as a part of the All of Us Research Program – thereby enabling other large-scale sequencing efforts with a comprehensive set of tools to power analysis.

This robust infrastructure deployment provisions:
    - An Amazon Virtual Private Cloud (VPC) with the needed networking components to process clinical samples securely
    - An AWS Batch job management system
    - A workflow orchestration system that comprises of serverless AWS Lambda functions and Amazon Simple Notification Service (SNS) topics that respond to the appearance of specific data files
    - Multiple software containers (available in DockerHub) for jobs that carry out standardized bioinformatics pipeline steps
    - A CloudWatch EventBridge and serverless system that automatically handles job failures and resubmissions due to Spot Instance interruption, and S3 lifecycle rules that automatically handle archival and cleanup for pipeline outputs
    - Infrastructure as Code (IaC) captured via CloudFormation templates, that deploy the above complete with Lambda functions containing specific bioinformatic software command-line parameters and a data-tagging system for use in data lifecycle management. 

The bioinformatics pipeline packaged within Celeste is suitable for clinical and population-scale sequencing projects. In the present day, a maximum of approximately 300-400 thousand jobs, related to human whole genome sequencing analysis, flow through Celeste monthly. 

![Hybrid Cloud](https://user-images.githubusercontent.com/35316399/195458866-5ea07ba1-e7ed-4af5-9e78-b3ebd0dea91b.png)

* Webinar resource: https://pages.awscloud.com/GLOBAL-field-OE-allofus-on-demand-2021-confirmation.html?aliId=eyJpIjoiWWVnNW5oSEZCMGE3TnJCZCIsInQiOiJqbFZZajE0azBwUnB6UkNqMUUzQ2dBPT0ifQ%253D%253D
* AWS Public Sector Blog Post: https://aws.amazon.com/blogs/publicsector/building-resilient-scalable-clinical-genomics-pipeline-aws/

# DEPLOYMENT GUIDE #
---
## Download Genomics Software Containers from DockerHub and Push to ECR ###
* Instructions pending
## Create the Genomics S3 Bucket ##
* Bucket creation for the environment happens separately from the rest of the stack(s) creation. Ideally, bucket creation is meant to occur only once in any given environment to create that environment's bucket (e.g.: "staging" in the staging environement)
* The bucket created will have a retention policy that specifies that it cannot be deleted even if the CloudFormation (CFn) stack is deleted
* The standalone template included within the templates/ directory will provision a versioned bucket with AES256 server side encryption enabled. The lifecycle configuration for *archive* tags will also be provisioned.
* First, clone the Celeste repository
* Ensure you are working in us-east-1 by running $ `aws configure`
* Upload the file **templates/s3-config.standalone.yaml** to a space in S3
    - `aws s3 cp templates/s3-config.standalone.yaml s3://${QSS3BucketName}/${QSS3KeyPrefix}templates/s3-config.standalone.yaml`
* Navigate to the AWS Management Console and ensure you are working in us-east-1. 
* Navigate to *CloudFormation* and select *Create Stack*
    - Select *"Template is ready"* and *"Amazon S3 URL"*
    - Enter the https URL for the template *templates/s3-config.standalone.yaml* (in the form: https://<S3_BUCKET>.s3.amazonaws.com/<S3_PREFIX>/s3-config.standalone.yaml)
* Enter bucketname for *Stack Name*
* Enter bucketname for the *S3 Bucket* parameter
* Page through, hitting *Next* until you see **Configure stack options.**
* Page through hitting "Next" until you see "Create Stack." Create Stack!
* Navigate to the S3 service page from the AWS Management Console to check that the bucket was created. You will see the resulting bucket has versioning enabled, AES256 encryption enabled, and lifecycle configuration rules for archives by clicking through the various *Properies* and *Management* tabs.
## Provision all Environment Resources ##
* Upload the git repo to the following space in S3:
    - $ `cd git repo`
    - $ `aws s3 sync . s3://${QSS3BucketName}/${QSS3KeyPrefix} --exclude ".git"` 
* You will use the https S3URL for **templates/celeste.yaml** to launch DRAGEN and HGSC-CL QC reports resources into a new VPC.
* Note that the templates all contain environment mappings (for unique dev, test, staging, and prod environments). Test is only used as a temporary environment to spawn resources and ensure viable templates. Resources with non-unique physical IDs in "test", "dev", "staging", and "prod" environments will have an associated suffix (e.g. "dragen-test" or "dragen-prod").
* From the correct env branch in your local copy of the repo, issue the following command:
    - $ `aws cloudformation create-stack --stack-name <SOMENAME> --template-url <HTTPS_URL_TO_MASTER.YAML> --parameters file://<PATH_TO_LOCAL_REPO>ci/params.json --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND --tags Key=env,Value=PROD`
* This process will take approximately **30 minutes**.
* You can log into the AWS Management Console and navigate to the CloudFormation service page for a more visual/intuitive understanding of what stage the stack creation is in.
* *WHEN YOU SEE THE GREEN CHECKMARK AND "CREATE COMPLETE" ON ALL 14 STACKS, EVERYTHING HAS BEEN SUCCESSFULLY PROVISIONED!*
* Everything from the AWS Batch compute environments (with the correct instance types and spot bids), to the AWS Lambda functions providing workflow automation, to the IAM roles/policies and more have now been provisioned!!!
## Ensure Proper Connectivity ##
* Finally, ensure the S3 Bucket you created at the beginning of this guide is connected to the resources that were successfully provisioned.
    - Navigate to the S3 service page from the AWS Management Console
    - Click the bucket created earlier and select *Properties*
    - Under *Events* click *Add new notification* and ensure the following are specified
    Parameter |   Value
    :--- |     :--- 
    **Name** |    *new-object-clinical-dragen-pipeline*
    **Event** |    *PUT,POST,COPY,Multipart upload completed*
    **Prefix** |    *clinical-dragen-pipeline*
    **Send To** |    *SNS Topic*
    **SNS Topic** | *NewObjectSNSTopic-prod*
* Ensure all jobs meant for the prod environment are subbed to the queues ending in the suffix *-prod* and that all job definitions also end with this suffix.
---
# Other Notes; FYI #
## To Deploy Only the Reports Resources ## 
* In the AWS Management Console, navigate to *CloudFormation* and select *Create Stack*.
* Use the https S3URL for **templates/reports-batch-9.19.parent.yaml** as the cloudformation parent template to launch resources in an existing VPC with two private subnets
## Breakdown of Nesting Relationships ##
* celeste.yaml: parent template for dragen-3.4.12.yaml, reports-batch-9.19.parent.yaml
* dragen-3.4.12.yaml: Refers to dragen AMI 3.4.12; parent template for docker-bucket-repository.yaml, copy.yaml, container-build.yaml, dragen-batch.yaml, and clean-bucket-repository.yaml
* dragen-batch.yaml: parent template for batch-roles.yaml
* clean-bucket-repository.yaml: parent for clean-bucket.yaml and clean-repository.yaml
* reports-batch-9.19.parent.yaml: parent for batch-roles.yaml and sns-lambdas.yaml
### Standalone Templates ###
* s3-config.standalone.yaml
* job-tracker-resub-handler.standalone.yaml
---
# NOTICE #
* All contents within this project are either original work from the BCM HGSC-CL, or unchanged works or derivatives from the "Illumina DRAGEN on AWS" QuickStart (source code: https://github.com/aws-quickstart/quickstart-illumina-dragen)
