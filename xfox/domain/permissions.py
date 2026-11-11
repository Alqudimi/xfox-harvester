"""Role-based access control matrix.

One explicit mapping from :class:`~xfox.domain.enums.Role` to the set of
:class:`~xfox.domain.enums.Permission` it grants. The API layer only ever asks
"does the current user hold permission X?" — never "what role is this user?".
"""

from xfox.domain.enums import Permission, Role

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.OPERATOR: frozenset(
        {
            Permission.ACCOUNTS_READ,
            Permission.ACCOUNTS_MANAGE,
            Permission.PROXIES_READ,
            Permission.PROXIES_MANAGE,
            Permission.JOBS_READ,
            Permission.JOBS_MANAGE,
            Permission.DATA_READ,
            Permission.DATA_EXPORT,
            Permission.EVENTS_READ,
            Permission.SETTINGS_READ,
            Permission.SYSTEM_READ,
        }
    ),
    Role.VIEWER: frozenset(
        {
            Permission.ACCOUNTS_READ,
            Permission.PROXIES_READ,
            Permission.JOBS_READ,
            Permission.DATA_READ,
            Permission.EVENTS_READ,
            Permission.SETTINGS_READ,
            Permission.SYSTEM_READ,
        }
    ),
}


def permissions_for(role: Role) -> frozenset[Permission]:
    """Return the permission set granted to *role*."""
    return ROLE_PERMISSIONS[role]


def role_has(role: Role, permission: Permission) -> bool:
    """True when *role* grants *permission*."""
    return permission in ROLE_PERMISSIONS[role]
