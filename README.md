# FH-613-Programming-Project
## Project for AI-assisted system for monitoring and validating RMIT Ads landing pages

## Project Overview
The Goal for this project is to design and develop an AI-assisted automated system that will help the RMIT Marketing Team to monitor and validate the content of approximately 650+ course landing pages. It replaces the inefficient manual process of daily page checks with an automated workflow that keeps an eye on HTTP status codes, and provides daily email summaries to stakeholders. The primary goal is to eliminate the time-consuming manual process of checking each and every page daily for critical updates. The system’s ability to get information fast and accurately ensures that the marketing team's advertisements are always up to date, which ensures that RMIT’s advertising information remains accurate across all campaigns.

### The Core Problem
Currently, the project faces several key challenges:
*   Operational inefficiency and a lack of communication between the various teams responsible for updating course information on the RMIT website.
*   No unified change-tracking mechanism.
*   Inconvenient to manually check 650+ pages every day.
*   No existing process for tracking newly added courses, updates to existing courses, or changes in application statuses.
*   Lack of communication between the teams managing course information and the marketing team, resulting in a lag in information transfer.
*   High risk of outdated or incorrect advertisements.

### Project Goal & Deliverables
The ultimate goal is to deliver an AI-assisted system that fully automates the monitoring of RMIT's ad landing pages. Key Deliverables:
*   An automated system that scans a predefined list of RMIT course URLs daily.
*   Automated daily email notifications sent to the marketing team, summarizing the status of all monitored pages, even if there are no changes.
*   A system to store a daily log or report of the status of each monitored page within a structured folder system.

### Core Functionality & Technical Requirements
The system must be able to perform the following actions automatically:
*   **Content Change Detection:** The system needs to specifically monitor the following key data points on each course page:
    *   Application Open Date
    *   "Apply Now" button/link status
    *   Application Close Date
*   **HTTP Status Monitoring:** Beyond content, the system must check the technical health of each URL and report on HTTP status codes (e.g., 200 for success, 404 for not found, 500 for server error).
*   **Automated Email Notifications:** Daily emails must be sent to the marketing team. These emails should provide a clear and concise report of any changes detected and confirm the status of pages with no changes.
*   **Data Logging and Storage:** The daily status of each course page must be saved. The client has specifically requested that these reports be organized into a representative folder structure.

### Technical Stack
*   **Languages:** Python (Backend), HTML/CSS (Frontend).
*   **Cloud Platform:** Amazon Web Services (AWS).
*   **Code Repository:** GitHub.
*   **SSH Client:** PuTTY.

---

## AWS Services Utilized

| Service | Name | Role and Function | Key Configuration |
| :--- | :--- | :--- | :--- |
| **Amazon EC2** | `RMIT-Google-Ads-AI-2025-Server` | Hosts the web front-end and initiates the scanning process. | VPC: `RMIT-App-vpc-vpc`, AMI: Ubuntu, Type: T3 Medium, Key: `RMIT-Ads-App-Key` |
| **AWS Lambda** | `2025RMIT-URL-Scanner` (main), `url-job-scheduler2025`, `FileProcessingLambda2025` | Serverless functions for parsing files and scheduling daily checks. | S3 Trigger, Environment variables for S3 bucket, recipients, etc. |
| **Amazon DynamoDB**| `url-processing-jobs` | A NoSQL database for storing structured metadata from every scan. | N/A |
| **Amazon S3** | `rmit-url-scan-data` | Primary storage for input `.xlsx` files and daily processed reports. | `processed/` and `source/` folders. |
| **Amazon SES** | `rmitaiteam@gmail.com` | Sends the daily summary and alert emails to stakeholders. | N/A |
| **EventBridge** | `Schedule` | Triggers the entire process on an automated daily schedule. | N/A |
| **AWS IAM** | `Rmit-workload-ads-serve`, `2025RMIT-URL-Scanner-role-q8v5o4o6` | Manages secure roles and permissions between AWS services. | FullAccess policies for DynamoDB, S3, SES, etc. |

---

## AWS Service Configuration Details 
This section covers a detailed visual overview of the AWS services and their configurations as used for this project. 

#### VPC + Security Groups:
This application’s infrastructure is isolated within a custom VPC named RMIT-App-vpc-vpc. The default security group acts as a stateful firewall, controlling the inbound and outbound traffic to the EC2 instance. 

*   **VPC General Configuration:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/vpc.png" alt="VPC General Configuration" width="700">

*   **VPC Resource Map:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/vpc_s2.png" alt="VPC Resource Map" width="700">

*   **Security Group Rules:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/security_groups_details.png" alt="Security Group Rules" width="700">

#### EC2:
The web application front-end and backend server are hosted on a single t3.medium EC2 instance named RMIT-Google-Ads-AI-2025-Server. 

*   **EC2 Instance Summary:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/ec2_s1.png" alt="EC2 Instance Summary" width="700">

*   **EC2 Security Details:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/ec2_s2.png" alt="EC2 Security Details" width="700">

#### Amazon S3 + DynamoDB: 
*   **Amazon S3 ->** The rmit-url-scan-data bucket serves as the primary storage for data for the application. 

    *   **S3 Bucket Structure:**
        <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/s3.png" alt="S3 Bucket Structure" width="700">

    *   **S3 Access Control:**
        <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/s3_s2.png" alt="S3 Access Control" width="700">

*   **DynamoDB ->** A NoSQL table named url-processing-jobs offers a historical log of all scan activities. 

    *   **DynamoDB Table details:**
        <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/dynamodb-table.png" alt="DynamoDB Table Details" width="700">

#### AWS Lambda: 
The core automation and data processing data tasks are managed by several serverless Lambda functions. 

**Primary Function: `2025RMIT-URL-Scanner`**
*   **Overview:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda.png" alt="Lambda Main Overview" width="700">
*   **Code properties + Layers:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s2.png" alt="Lambda Main Code Properties" width="700">
*   **Timeout + Memory Config:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s3.png" alt="Lambda Main Configuration" width="700">
*   **Environment variables:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s4.png" alt="Lambda Main Environment Variables" width="700">
*   **Execution Role permissions:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s5.png" alt="Lambda Main Execution Role" width="700">

**Scheduler Function: `url-job-scheduler2025`**
This function was made to be the target of a schedule trigger, responsible for starting the overall job workflow. 

*   **Overview:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s6.png" alt="Lambda Scheduler Overview" width="700">
*   **Timeout + Memory Config:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s7.png" alt="Lambda Scheduler Configuration" width="700">
*   **Code properties:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s8.png" alt="Lambda Scheduler Code Properties" width="700">
*   **Execution Role permissions:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s9.png" alt="Lambda Scheduler Execution Role" width="700">

**File Processing Function: `FileProcessingLambda2025`**
This function manages the validation and processing of the newly uploaded .xlsx file in the S3 bucket. 

*   **Overview:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s10.png" alt="Lambda FileProcessing Overview" width="700">
*   **Code properties:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s11.png" alt="Lambda FileProcessing Code Properties" width="700">
*   **Timeout + Memory Config:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/lambda_s12.png" alt="Lambda FileProcessing Configuration" width="700">

#### AWS EventBridge:
It is used to automate the entire process. 

*   **Scheduled Rules:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/eventbridge.png" alt="EventBridge Scheduled Rules" width="700">

#### Amazon SES: 
Configured to manage the sending of all email notifications. 

*   **Verified Identities:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/ses.png" alt="SES Verified Identities" width="700">

#### AWS IAM:
It provides the security backbone of the applications managing permissions. 

*   **IAM roles:**
    <img src="C:\Users\harsh\FH-613-Programming-Project\FH-613-Programming-Project\Screenshots for ReadMe/iam.png" alt="IAM Roles" width="700">

---

## How To Deploy

### Prerequisites
Make sure you have the following before you start:
*   **Access to the AWS Management Console:** Login credentials with sufficient rights to view EC2, S3, and other associated services.
*   **GitHub Repository Access:** Access to the project's GitHub repository in order to clone the source code.
*   **Client for PuTTY SSH:** Install PuTTY from the official website.
*   **Private Key File:** `RMIT-Ads-App-Key.ppk`. This key is private and needs to be kept in a safe place.
*   **Public IP address of an EC2 instance:** Found by navigating to the EC2 service in the AWS Management Console and selecting the `RMIT-Google-Ads-AI-2025-Server` instance.

### 1. Establish a Secure Connection
First, we will establish a secure connection to the server where the web application will be hosted.
1.  **Launch PuTTY:** Open the PuTTY application.
2.  **Enter Host Name:** In the `Host Name (or IP address)` field, enter the public IP address of the instance.
3.  **Load the Private Key:**
    *   In the left-hand menu, navigate to `Connection -> SSH -> Auth`.
    *   Click the **Browse...** button next to the `Private key file for authentication` field.
    *   Locate and select your `ppk` key file.
4.  **Connect:** Click the **Open** button. A terminal window will appear.
5.  **Login:** The server is an Ubuntu instance, so the default username is `ubuntu`. When prompted for "login as:", type `ubuntu` and press Enter.

### 2. Install Software & Download Code
Now we will install the necessary software and download the application code.

**Update Server Packages:**
```bash
sudo apt update && sudo apt upgrade -y
```

**Install Required Software:**
```bash
sudo apt install python3-pip python3-venv git -y
```

**Clone the Application from GitHub:**
```bash
git clone [URL of your GitHub repository]
```
*(Replace `[URL of your GitHub repository]` with the actual link.)*

**Navigate to the Project Directory:**
```bash
cd [repository-name]
```
*(Replace `[repository-name]` with the folder name created by the clone command.)*

### 3. Set Up Application Environment

**Create a Python Virtual Environment:**
```bash
python3 -m venv venv
```

**Activate the Virtual Environment:**
```bash
source venv/bin/activate
```
*(Your command prompt will be prefixed with `(venv)`.)*

**Install Python Dependencies:**
```bash
pip install -r requirements.txt
```
*(Note: If a `requirements.txt` file does not exist, you must create one by running `pip freeze > requirements.txt` on a working machine and commit it to the repository.)*

### 4. Deploy with Gunicorn and Nginx

**Install Gunicorn:**
```bash
pip install gunicorn
```

**Create a systemd Service File:**
```bash
sudo nano /etc/systemd/system/rmit-google-ads-ai.service
```
Copy and paste the following content into the file. You must adjust the paths to match your server setup:
```ini
[Unit]
Description=Gunicorn instance to serve RMIT Google Ads AI
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/var/www/rmit-google-ads-ai/FH-613-Programming-Project
Environment="S3_BUCKET_NAME=rmit-url-scan-data"
ExecStart=/var/www/rmit-google-ads-ai/FH-613-Programming-Project/venv/bin/gunicorn --workers 3 --bind unix:rmit-google-ads-ai.sock -m 007 wsgi:app

[Install]
WantedBy=multi-user.target
```

**Start and Enable the Service:**
```bash
sudo systemctl start rmit-google-ads-ai.service
sudo systemctl enable rmit-google-ads-ai.service
```
Check the status to ensure it's running without errors:
```bash
sudo systemctl status rmit-google-ads-ai.service
```

**Install Nginx:**
```bash
sudo apt install nginx -y
```

**Create an Nginx Configuration File:**
```bash
sudo nano /etc/nginx/sites-available/rmitapp
```
Paste the following configuration:
```nginx
server {
    listen 80;
    server_name your_domain_or_ip;

    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://unix:/var/www/rmit-google-ads-ai/FH-613-Programming-Project/rmit-google-ads-ai.sock;
        proxy_buffering off;
        proxy_set_header X-Accel-Buffering no;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Enable the Configuration:**
```bash
sudo ln -s /etc/nginx/sites-available/rmitapp /etc/nginx/sites-enabled
```
Test for syntax errors and restart Nginx:
```bash
sudo nginx -t
sudo systemctl restart nginx
```

**Verify the Application is Running:**
Open your web browser and navigate to `http://<your_ec2_ip_address>`. You should see the index.html page.

---

## Post-Deployment Verification

The final step is to ensure your deployed application is correctly interacting with all the configured AWS services.

### Perform an End-to-End Test:
1.  Use the web interface to upload a sample `URL.xlsx` file.
2.  Go to the **Amazon S3 console**. In the `rmit-url-scan-data` bucket, verify that your uploaded file appears in the `source/` folder.
3.  The file creation should automatically trigger the `2025RMIT-URL-Scanner` Lambda function. Go to the **AWS Lambda console**, find the function, and check its "Monitor" tab for recent invocations and logs in CloudWatch.
4.  Go to the **DynamoDB console** and view the items in the `url-processing-jobs` table. A new entry for your job should appear.
5.  After the Lambda function finishes, check the `processed/` folder in the S3 bucket. The processed file with the results should appear here.
6.  Check the inbox of the recipient email (`rmitaiteam@gmail.com`). You should receive a notification email. *(Reminder: This will only work if SES is out of sandbox mode).*

---

## Troubleshooting
*   **Cannot connect with PuTTY:** Double-check the IP address and ensure you are using the correct `.ppk` private key file.
*   **Website doesn't load (Connection Timed Out):** Check the EC2 instance's Security Group. It must allow inbound HTTP traffic on port 80 from your IP.
*   **Website shows "Internal Server Error":** The application crashed. SSH into the server and check the application logs for errors (`sudo journalctl -u rmit-google-ads-ai.service`).
*   **File uploads but is not processed:**
    *   Check the Lambda function's logs in **Amazon CloudWatch**. This is the most common place to find permission errors or code bugs.
    *   Verify the S3 trigger on the Lambda function is correctly configured for the `source/` folder.
    *   Ensure the Lambda's IAM role (`2025RMIT-URL-Scanner-role-q8v5o4o6`) has the required permissions.

---

## Current Status, Blockers, and Known Issues
The system's fundamental functionality has been built but is not yet production-ready due to two significant obstacles.

*   **Blocker 1: Amazon SES Sandbox Mode (High Priority):**
    The Amazon Simple Email Service (SES) account is in "sandbox mode," which restricts sending emails only to verified addresses. The system cannot send the daily report to the real stakeholders. The next team must work with the client to request production access from AWS.
*   **Blocker 2: Automated Scheduling Not Functional (High Priority):**
    The AWS EventBridge scheduling function is not operating as expected, requiring the daily scan to be started manually. Debugging the EventBridge setup and its integration with the Lambda function is a critical next step.

---

## Recommended steps for the Next Team

### Fixes
*   **Automated Scheduling:** Dedicate time to debugging the AWS EventBridge trigger until the process is truly automated.

### Enhancements:
*   **Folder Structure:** Consider implementing the original requirement of organizing the S3 reports into a hierarchical folder structure (e.g., `year/month/day/report.csv`).
*   **Change Detection:** Improve the change detection logic beyond status codes to include checks for application dates, status (open/closed), and the school it belongs to, as per the client's request.

### Phase 2
*   **API Gateway:** Begin work on the planned Phase 2 by building an API Gateway. This would allow other RMIT systems to programmatically interact with your service, greatly increasing its utility.

---

## Credentials
*   **PuTTY:** `3.24.74.191`, get key from client.
*   **Email:** Get from client.
*   **URL:** `http://urlchecker.rmitchatgptai.com/`