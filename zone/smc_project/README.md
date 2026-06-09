# CivikZone_Solution
Django-based Civic Complaint Management System where citizens submit complaints and officers/admins manage assignment, status updates, feedback, duplicate detection, and audit timeline tracking through a structured web interface.

## SQLite Configuration

Project is configured to use SQLite as the default database for local development.

The database file is stored at `db.sqlite3`.

Run database migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```
