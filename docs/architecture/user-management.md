# User management

Keycloak is the source of truth for who may use OpsPilot and with which role.
OpsPilot never stores passwords and never changes roles.

## How users appear in OpsPilot

1. A user signs in through Keycloak; the API verifies the access token.
2. On the first request the user row is created in the token's organization
   (`user.provisioned` audit record).
3. On every request the user's roles are replaced by the application realm
   roles in the token (`viewer`, `operator`, `incident-commander`,
   `administrator`); other realm roles are ignored.

So the roles OpsPilot shows are those from each user's latest sign-in. A role
removed in Keycloak disappears from OpsPilot on that user's next request; a
user disabled in OpsPilot (`status = disabled`) is refused even with a valid
token.

## Endpoints (read-only)

Both require the `manage_users` permission (administrators only) and only
return users of the caller's organization; a user in another organization is
reported as 404.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/v1/users?limit=&cursor=` | Users newest first, with roles and the permissions those roles grant; keyset-paginated via `next_cursor` |
| `GET` | `/api/v1/users/{user_id}` | One user |

## Changing access

Grant, revoke, or change roles in the Keycloak admin console (realm
`opspilot`, Users → Role mapping). There are deliberately no write endpoints:
a second place to edit roles would drift from the identity provider.
