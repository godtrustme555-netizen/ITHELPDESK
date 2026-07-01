# Production Deployment Guide for Ubuntu 24.04 LTS

This playbook provides a step-by-step guide to deploying the IT Helpdesk Project in a secure, production-ready environment configured to support 100 users, 20 concurrent users, and 500+ tickets per month.

## Architecture Stack
- **OS**: Ubuntu 24.04 LTS
- **Database**: PostgreSQL 16+
- **WSGI Application Server**: Gunicorn
- **Reverse Proxy & Web Server**: Nginx
- **SSL/TLS**: Certbot (Let's Encrypt)
- **Backup**: Daily automated PostgreSQL dump shell script + Cron

---

## Step 1: System Preparation & Prerequisites

1. Update system packages to their latest versions:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. Install system packages (Python, PostgreSQL, Nginx, Certbot):
   ```bash
   sudo apt install -y python3-pip python3-venv python3-dev \
                       postgresql postgresql-contrib \
                       nginx certbot python3-certbot-nginx \
                       curl git acl
   ```

---

## Step 2: Configure PostgreSQL Database

1. Connect to the default PostgreSQL console:
   ```bash
   sudo -i -u postgres psql
   ```

2. Create a database, a dedicated database user, and assign permissions:
   ```sql
   CREATE DATABASE helpdesk_db;
   CREATE USER helpdesk_user WITH PASSWORD 'choose_a_strong_password_here';
   ALTER ROLE helpdesk_user SET client_encoding TO 'utf8';
   ALTER ROLE helpdesk_user SET default_transaction_isolation TO 'read committed';
   ALTER ROLE helpdesk_user SET timezone TO 'UTC';
   GRANT ALL PRIVILEGES ON DATABASE helpdesk_db TO helpdesk_user;
   \q
   ```

---

## Step 3: Set Up Project Files & Permissions

1. Create a root directory for the application:
   ```bash
   sudo mkdir -p /var/www/helpdesk
   sudo chown -R $USER:www-data /var/www/helpdesk
   sudo chmod -R 775 /var/www/helpdesk
   ```

2. Clone or copy your project files into `/var/www/helpdesk`. Ensure the directory contains `manage.py`, `helpdesk/`, `accounts/`, `tickets/`, `requirements.txt`, etc.

---

## Step 4: Configure the Virtual Environment

1. Create a virtual environment inside the project directory:
   ```bash
   cd /var/www/helpdesk
   python3 -m venv venv
   ```

2. Activate the virtual environment and install production dependencies:
   ```bash
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## Step 5: Configure Production Environment Variables

1. Copy `.env.example` to create the production `.env` file:
   ```bash
   cp .env.example .env
   ```

2. Generate a secure, production-ready `SECRET_KEY`:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(50))"
   ```

3. Open `.env` and fill out your variables:
   ```bash
   nano .env
   ```
   * Ensure:
     - `DEBUG=False`
     - `SECRET_KEY` is set to the generated key.
     - `ALLOWED_HOSTS` includes your domain (e.g. `helpdesk.yourdomain.com`).
     - `DATABASE_URL` is set to: `postgres://helpdesk_user:your_secure_password_here@localhost:5432/helpdesk_db`
     - `SITE_URL` is your public URL (`https://helpdesk.yourdomain.com`).
     - `EMAIL_*` fields contain your production SMTP mail server credentials.

4. Secure the `.env` file from public reading:
   ```bash
   chmod 600 .env
   ```

---

## Step 6: Log Directory and Web Directories

1. Create the unified logs directory:
   ```bash
   sudo mkdir -p /var/log/helpdesk
   sudo chown -R www-data:www-data /var/log/helpdesk
   sudo chmod -R 775 /var/log/helpdesk
   ```

2. Create media uploads directory and set permissions:
   ```bash
   mkdir -p /var/www/helpdesk/media
   sudo chown -R www-data:www-data /var/www/helpdesk/media
   sudo chmod -R 775 /var/www/helpdesk/media
   ```

3. Run migrations and collect static files:
   ```bash
   source venv/bin/activate
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```

4. Ensure all files under the project are accessible to `www-data`:
   ```bash
   sudo chown -R www-data:www-data /var/www/helpdesk/staticfiles
   ```

---

## Step 7: Configure Gunicorn

1. Copy the systemd files to the system services directory:
   ```bash
   sudo cp gunicorn.socket /etc/systemd/system/gunicorn.socket
   sudo cp gunicorn.service /etc/systemd/system/gunicorn.service
   ```

2. Enable and start the Gunicorn service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start gunicorn.socket
   sudo systemctl enable gunicorn.socket
   ```

3. Verify that the socket file `/run/gunicorn.sock` is created:
   ```bash
   sudo systemctl status gunicorn.socket
   ```

---

## Step 8: Configure Nginx Reverse Proxy

1. Copy Nginx configuration file:
   ```bash
   sudo cp nginx.conf /etc/nginx/sites-available/helpdesk
   ```

2. Replace references to `helpdesk.example.com` in `/etc/nginx/sites-available/helpdesk` with your actual domain name:
   ```bash
   sudo nano /etc/nginx/sites-available/helpdesk
   ```

3. Enable the virtual host configuration by creating a symlink:
   ```bash
   sudo ln -sf /etc/nginx/sites-available/helpdesk /etc/nginx/sites-enabled/
   ```

4. Test Nginx syntax and reload:
   ```bash
   sudo nginx -t
   sudo systemctl restart nginx
   ```

---

## Step 9: Configure SSL Certificate (Let's Encrypt)

1. Obtain and install the TLS certificate from Let's Encrypt:
   ```bash
   sudo certbot --nginx -d helpdesk.yourdomain.com
   ```
   *Certbot will automatically verify the domain, obtain the certificate, and update the Nginx configuration with HTTPS listeners and security headers.*

2. Test automated certificate renewal (Certbot sets up a cron/systemd timer automatically):
   ```bash
   sudo certbot renew --dry-run
   ```

---

## Step 10: Set Up Database Backups

1. Copy the backup script to a secure location:
   ```bash
   sudo mkdir -p /var/backups/helpdesk
   sudo cp backup_db.sh /var/backups/helpdesk/backup_db.sh
   sudo chmod 700 /var/backups/helpdesk/backup_db.sh
   sudo chown root:root /var/backups/helpdesk/backup_db.sh
   ```

2. Configure a cron job for the root user to run it daily at 2:00 AM:
   ```bash
   sudo crontab -e
   ```
   Add the following line at the bottom:
   ```text
   0 2 * * * /var/backups/helpdesk/backup_db.sh
   ```

---

## Step 11: Setup Firewall (UFW)

1. Configure firewall rules to secure the server, only allowing SSH, HTTP, and HTTPS:
   ```bash
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow OpenSSH
   sudo ufw allow 'Nginx Full'
   sudo ufw enable
   ```

---

## Step 12: Verification and Troubleshooting

### Manage Services
- **Restart Django / Gunicorn**: `sudo systemctl restart gunicorn`
- **Restart Nginx**: `sudo systemctl restart nginx`
- **View Gunicorn Status**: `sudo systemctl status gunicorn`

### Monitoring Logs
All project-specific logs are consolidated under `/var/log/helpdesk/`:
- **Django Application Logs**: `tail -f /var/log/helpdesk/django.log`
- **Errors**: `tail -f /var/log/helpdesk/errors.log`
- **User Activity Audit Trail**: `tail -f /var/log/helpdesk/security.log`
- **Backup Script Logs**: `cat /var/log/helpdesk/backup.log`
- **Nginx Error Logs**: `tail -f /var/log/nginx/error.log`
