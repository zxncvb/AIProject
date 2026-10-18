import ssl
from typing import Any

from ldap3 import AUTO_BIND_NO_TLS, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from ..config import get_settings


class LDAPError(RuntimeError):
    pass


def authenticate(email: str, password: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.ldap_url or not settings.ldap_user_search_base:
        raise LDAPError("LDAP 尚未配置")
    tls = Tls(validate=ssl.CERT_REQUIRED if settings.ldap_tls_verify else ssl.CERT_NONE)
    server = Server(settings.ldap_url, use_ssl=settings.ldap_url.lower().startswith("ldaps://"), tls=tls, connect_timeout=10, get_info=None)
    service = None
    try:
        service = Connection(server, user=settings.ldap_bind_dn or None, password=settings.ldap_bind_password or None, auto_bind=AUTO_BIND_NO_TLS, raise_exceptions=True)
        search_filter = settings.ldap_user_search_filter.replace("{email}", escape_filter_chars(email))
        if not service.search(settings.ldap_user_search_base, search_filter, attributes=["mail", "displayName", "cn"]):
            raise LDAPError("LDAP 用户不存在")
        entry = service.entries[0]
        user_dn = entry.entry_dn
        service.rebind(user=user_dn, password=password)
        attributes = entry.entry_attributes_as_dict
        return {
            "email": str((attributes.get("mail") or [email])[0]).lower().strip(),
            "display_name": str((attributes.get("displayName") or attributes.get("cn") or [email])[0]),
        }
    except LDAPException as exc:
        raise LDAPError("LDAP 用户名或密码错误") from exc
    finally:
        if service:
            service.unbind()
