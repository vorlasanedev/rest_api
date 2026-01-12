Add readme
1. login

Method: POST
header: 
X-API-Key: <your_api_key>
content-type: application/json
body: 
{
    "login": "secure_user@example.com",
    "password": "Mypassword123!"
}
2. logout

Method: POST
URL: /api/logout
Authentication: 
    type: bearer
    value: <your_api_key>
header: 
content-type: application/json


Operation CRUD	Method	URL	Notes
Create	POST	/api/v1/res.users	Checks for duplicates, auto-generates API Key

CRUD1-> Method: POST
URL: /api/v1/res.users
Authentication: 
    type: bearer
    value: <your_api_key>
header: 
content-type: application/json
body: 
{
    "name": "Secure User",
    "login": "secure_user@example.com",
    "email": "secure_user@example.com",
    "password": "Mypassword123!"
}

CRUD2-> Read	GET	/api/v1/res.users/[ID]	Returns user data

Method: GET
URL: /api/v1/res.users/[ID]
Authentication: 
    type: bearer
    value: <your_api_key>
header: 
content-type: application/json

CRUD3-> Update	PUT	/api/v1/res.users/[ID]	Updates fields (and validates password if sent)

Method: PUT
URL: /api/v1/res.users/[ID]
Authentication: 
    type: bearer
    value: <your_api_key>
header: 
content-type: application/json
body: 
{
    "name": "Secure User"
}
CRUD4-> Delete	DELETE	/api/v1/res.users/[ID]	Deletes the user

Method: DELETE
URL: /api/v1/res.users/[ID]
Authentication: 
    type: bearer
    value: <your_api_key>
header: 
content-type: application/json
