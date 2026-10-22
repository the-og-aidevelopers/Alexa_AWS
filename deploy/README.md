# Deploy Pillow on AWS

One small EC2 server, with everything else handled by managed AWS services:

| Piece | Service | Why |
| --- | --- | --- |
| Server | EC2 `t4g.micro` (arm64, about 100 MB of memory in use) | cheapest instance that runs it comfortably |
| Data | DynamoDB, one table, pay per request | no database server to run or back up |
| https address | CloudFront | gives a free `https://….cloudfront.net` address, which the microphone needs |
| Sign-in | Cognito Hosted UI | no passwords stored by us |
| Choosing the action | Bedrock (Amazon Nova Micro) | optional; the built-in rules are the fallback |

The server has no AWS keys on it. The instance role grants only the one DynamoDB table and the one Bedrock model.

## Steps

1. **Launch the instance** (region `us-east-1`): Amazon Linux 2023 arm64, `t4g.micro`, 8 GiB, public IP. Use User data to add the deploy key to `authorized_keys`. Security group: SSH from your IP only, HTTP 80 from the CloudFront prefix list `com.amazonaws.global.cloudfront.origin-facing`.
2. **Create the stack**: CloudFormation, Create stack, upload `deploy/aws.yaml`, and give the instance's public DNS name as `OriginDnsName`. It creates the table, the instance role, the CloudFront distribution and the Cognito pool, domain and client. Wait 5 to 10 minutes for CloudFront.
3. **Attach the role**: EC2, select the instance, Actions, Security, Modify IAM role, choose `pillow-ec2` (the stack's `InstanceProfileName` output).
4. **Bedrock access**: in the Bedrock console, make sure model access for Amazon Nova Micro is on for the region.
5. **Write the env file**: copy `pillow.env.example` to `pillow.env` and fill in the stack outputs (`CloudFrontDomain`, `UserPoolId`, `ClientId`, `CognitoDomain`). Set `DOSE_SECRET` to a long random string.
6. **Deploy**:
   ```bash
   HOST=ec2-….compute-1.amazonaws.com ENV_FILE=./pillow.env ./deploy/deploy.sh
   ```
   It builds the frontend, copies the app over, installs the Python packages in a virtual environment and starts a systemd service. Run it again without `ENV_FILE` for later updates.
7. Open `https://<CloudFrontDomain>`, press Sign in, create an account with your email, and you land in your own empty household.

## Cost, roughly per month

EC2 `t4g.micro` about $6 to $8, EBS 8 GiB under $1, DynamoDB and Cognito pennies at this size, CloudFront inside the free tier, Bedrock Nova Micro a fraction of a cent per request. Voice uses the browser's own speech recognition unless you set `ELEVENLABS_API_KEY` in the env file.

## Tear down

Delete the CloudFormation stack, then terminate the instance. The DynamoDB table goes with the stack, so export anything you want to keep first.
