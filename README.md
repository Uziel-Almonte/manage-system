# manage-system

## Running the Project

### Start the Containers
Run the project normally:
```bash
docker compose up -d
```

## Keycloak Setup (Authentication)
This project uses Keycloak for Identity and Access Management (IAM) and Role-Based Access Control (RBAC).

**1. Access the Keycloak Console:**
Navigate to `http://localhost:8080` in your browser.
Login with the admin credentials defined in your `.env` (default: `admin` / `admin_password`).

**2. Client Configuration (`flask-backend`):**
To ensure the Flask OAuth flow works perfectly, make sure your client in Keycloak has the following configured:
- **Client Authentication:** ON (Confidential access type)
- **Valid Redirect URIs:** `http://localhost:5000/auth/callback`
- **Valid post logout redirect URIs:** `http://localhost:5000/`

**3. Environment Variables:**
Copy the client secret from Keycloak's "Credentials" tab into your `.env` file under `KEYCLOAK_CLIENT_SECRET`.

To log in to the application, visit `http://localhost:5000/auth/login`.
