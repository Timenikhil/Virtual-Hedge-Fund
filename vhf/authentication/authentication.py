from typing import Callable, Annotated

from firebase_admin import auth
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin.auth import InvalidIdTokenError, UserNotFoundError

from vhf.authentication.initialiser import initialize_firebase_admin
from vhf.logging.log import logger
from vhf.models.user import FirebaseUser, UserRole, FirebaseUserE

initialize_firebase_admin()

# Security scheme for JWT tokens
security = HTTPBearer()

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
) -> FirebaseUser:
    """
    FastAPI dependency that validates Firebase JWT token and returns user information.

    Args:
        credentials: The JWT token from the Authorization header

    Returns:
        FirebaseUser: Object containing user_id and role

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Verify the Firebase token
        decoded_token = auth.verify_id_token(credentials.credentials)
        # Get role from custom claims, default to PUBLIC if not set
        role = decoded_token.get("role", UserRole.PUBLIC)

        return FirebaseUser(user_id=decoded_token["uid"], role=role)
    except (InvalidIdTokenError, ValueError) as e:
        # Catches expired, malformed, or invalid tokens
        logger.warn(f"Invalid token received: {e}",
                    extra={"Error" : str(e)})
        raise HTTPException(
            status_code=401, detail="Invalid authentication credentials"
        )
    except Exception as e:
        # Catch-all for other unexpected errors
        logger.error(f"Error in get_current_user: {e}", extra={"Error" : str(e)})
        raise HTTPException(
            status_code=500, detail="Error processing authentication token"
        )

async def get_current_user_email(
        credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
) -> FirebaseUserE:
    """
    FastAPI dependency that validates Firebase JWT token and returns user information.

    Args:
        credentials: The JWT token from the Authorization header

    Returns:
        FirebaseUser: Object containing user_id and role

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Verify the Firebase token
        decoded_token = auth.verify_id_token(credentials.credentials)
        # Get role from custom claims, default to PUBLIC if not set
        role = decoded_token.get("role", UserRole.PUBLIC)
        name = decoded_token.get("name")
        email = decoded_token.get("email")
        return FirebaseUserE(user_id=decoded_token["uid"], name = name,email = email,role=role)

    except (InvalidIdTokenError, ValueError) as e:
        # Catches expired, malformed, or invalid tokens
        logger.warn(f"Invalid token received: {e}",
                    extra={"Error" : str(e)})
        raise HTTPException(
            status_code=401, detail="Invalid authentication credentials"
        )
    except Exception as e:
        # Catch-all for other unexpected errors
        logger.error(f"Error in get_current_user: {e}", extra={"Error" : str(e)})
        raise HTTPException(
            status_code=500, detail="Error processing authentication token"
        )


def check_role(allowed_roles: list[UserRole]) -> Callable:
    """
    Creates a dependency that checks if the current user has one of the allowed roles.

    Args:
        allowed_roles: List of roles that are allowed to access the endpoint

    Returns:
        Callable: FastAPI dependency that checks user role
    """

    async def role_checker(
        user: Annotated[FirebaseUser, Depends(get_current_user)],
    ) -> FirebaseUser:
        if user.role not in allowed_roles:
            logger.warn(f"RoleCheck Failed: User {user.user_id} (Role: {user.role}) attempted to access endpoint restricted to {allowed_roles}",
                        extra = {
                            "User" : user.user_id,
                            "Role" : user.role,
                            "AllowedRoles" : allowed_roles,
                        })
            raise HTTPException(
                status_code=403,
                detail=f"User with role {user.role} is not permitted to access this endpoint",
            )
        return user

    return role_checker

async def assign_role(target:FirebaseUser, authorizer: FirebaseUser) -> None:
    """
    Assigns a role to a user by setting a custom claim in Firebase.

    Args:
        :param target:
            user_id: The Firebase UID of the user
            role: The role to assign to the user
        :param authorizer: The FirebaseUser object of the user authorizing the role change
    Raises:
        HTTPException: If the role assignment fails
    """
    user_id, role = target.user_id, target.role
    if authorizer.role != UserRole.CFL:
        logger.warn(f"User with id:{authorizer.user_id}, role: {authorizer.role} tried to assign role {role} to user {user_id}",
                    extra = {
                        "User" : user_id,
                        "Role" : role,
                        "Authorizer" : authorizer.user_id,
                        "AuthorizerRole" : authorizer.role,
                    })
        raise HTTPException(status_code=403, detail="User is not allowed to access this endpoint.")
    try:
        # Set custom claims in Firebase
        auth.set_custom_user_claims(user_id, {"role": role.value})
        logger.info(f"User with id:{authorizer.user_id} assigned role {role} to user {user_id}",
                    extra={"User" : user_id,
                           "Role" : role.value,
                           "Authorizer" : authorizer.user_id})
    except UserNotFoundError:
        logger.warn(f"Role Update Failed - User not found: {user_id} | Attempted by: {authorizer.user_id}",
                    extra={"User" : user_id,
                           "Authorizer" : authorizer.user_id})
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        logger.error(f"User with id:{authorizer.user_id} attempted to assign role {role} to user {user_id}",
                     extra={"Authorizer" : authorizer.user_id,
                            "User" : user_id,
                            "Role" : role.value})
        logger.error(f"Error: {str(e)}",
                     extra={"Error" : str(e)})
        raise HTTPException(status_code=400, detail=f"Failed to assign role: {str(e)}")

def updateName(userid:str,name: str):
    auth.update_user(userid,display_name=name)