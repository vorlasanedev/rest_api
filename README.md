# Odoo 18 REST API Module

## 1. Authentication
All requests (except `/api/login`) require the `X-API-Key` header.

### Login (Get API Key)
- **Method**: `POST`
- **URL**: `/api/login`
- **Body**: 
```json
{
    "login": "your_email@example.com",
    "password": "your_password",
    "db": "odoo18"
}
```

### Logout
- **Method**: `POST`
- **URL**: `/api/logout`

---

## 2. Metadata Discovery
Use this to see what fields are available for any model.

### List Available Fields
- **Method**: `GET`
- **URL**: `/api/v1/res.users/fields`
- **Header**: `X-API-Key: <your_key>`

---

## 3. CRUD Operations (`/api/v1/<model_name>`)

### Create (POST)
- **URL**: `/api/v1/res.users`
- **Body**: `{"name": "John", "login": "john@test.com", "password": "123", "confirm_password": "123"}`

### Read (GET)
- **Single**: `/api/v1/res.users/7`
- **Search**: `/api/v1/res.users?fields=["name","login"]&limit=10`

### Update (PUT)
- **URL**: `/api/v1/res.users/7`
- **Body**: `{"name": "Updated John"}`

### Delete (DELETE)
- **URL**: `/api/v1/res.users/7`
