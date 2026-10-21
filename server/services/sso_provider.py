"""
sso_provider.py — Enterprise Single Sign-On (SSO) & OIDC / SAML 2.0 Integration Engine
Supports OpenID Connect (OIDC) identity providers (Google Workspace, Microsoft Entra ID / Azure AD, Okta, Keycloak).
"""

import os
import json
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, Tuple

class OIDCProvider:
    def __init__(self, client_id: str, client_secret: str, discovery_url: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.discovery_url = discovery_url.rstrip("/")
        self.redirect_uri = redirect_uri
        self._endpoints: Dict[str, str] = {}

    def load_discovery(self) -> bool:
        """Fetches OpenID configuration discovery document (.well-known/openid-configuration)."""
        well_known = f"{self.discovery_url}/.well-known/openid-configuration"
        try:
            req = urllib.request.Request(well_known, headers={"User-Agent": "ArgosWorks-SSO/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._endpoints = {
                    "authorization_endpoint": data.get("authorization_endpoint"),
                    "token_endpoint": data.get("token_endpoint"),
                    "userinfo_endpoint": data.get("userinfo_endpoint"),
                    "jwks_uri": data.get("jwks_uri"),
                }
                return True
        except Exception as e:
            print(f"[SSO] Discovery failed for {well_known}: {e}")
            return False

    def get_authorization_url(self, state: str) -> str:
        """Constructs SSO login redirect URL."""
        auth_ep = self._endpoints.get("authorization_endpoint") or f"{self.discovery_url}/oauth2/v2/auth"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        return f"{auth_ep}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_user(self, code: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Exchanges auth code for tokens and extracts verified user identity profile."""
        token_ep = self._endpoints.get("token_endpoint") or f"{self.discovery_url}/oauth2/v2/token"
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }).encode("utf-8")

        try:
            req = urllib.request.Request(token_ep, data=data, method="POST", headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "ArgosWorks-SSO/2.0"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_resp = json.loads(resp.read().decode("utf-8"))
                access_token = token_resp.get("access_token")

            # Fetch user info
            userinfo_ep = self._endpoints.get("userinfo_endpoint") or f"{self.discovery_url}/oauth2/v2/userinfo"
            u_req = urllib.request.Request(userinfo_ep, headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "ArgosWorks-SSO/2.0"
            })
            with urllib.request.urlopen(u_req, timeout=10) as u_resp:
                user_info = json.loads(u_resp.read().decode("utf-8"))
                return True, {
                    "email": (user_info.get("email") or "").lower().strip(),
                    "name": user_info.get("name") or user_info.get("given_name") or "Enterprise User",
                    "sub": user_info.get("sub"),
                }
        except Exception as e:
            return False, None
