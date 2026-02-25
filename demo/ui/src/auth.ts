import NextAuth from "next-auth"
import Keycloak from "next-auth/providers/keycloak"

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Keycloak({
      clientId: process.env.AUTH_KEYCLOAK_ID,
      clientSecret: process.env.AUTH_KEYCLOAK_SECRET,
      issuer: process.env.AUTH_KEYCLOAK_ISSUER,
      // Use external URL for browser redirection
      authorization: {
        params: {
          scope: "openid profile email",
        },
        url: process.env.AUTH_KEYCLOAK_PUBLIC_URL || "http://localhost:8080/realms/fds/protocol/openid-connect/auth",
      },
      // Use internal URL for server-to-server communication
      token: process.env.AUTH_KEYCLOAK_INTERNAL_URL ? `${process.env.AUTH_KEYCLOAK_INTERNAL_URL}/protocol/openid-connect/token` : undefined,
      userinfo: process.env.AUTH_KEYCLOAK_INTERNAL_URL ? `${process.env.AUTH_KEYCLOAK_INTERNAL_URL}/protocol/openid-connect/userinfo` : undefined,
      // Fix for Docker: Load metadata from internal network, but validate issuer as external
      wellKnown: process.env.AUTH_KEYCLOAK_METADATA_URL,
    }),
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account) {
        token.accessToken = account.access_token
        token.idToken = account.id_token
      }

      // Extract scopes from the token
      // Prefer scopes from the ID Token (profile) as it contains our mapped client roles
      if (profile && 'scope' in profile) {
        const scope = profile.scope
        if (Array.isArray(scope)) {
           token.scopes = scope
        } else if (typeof scope === 'string') {
           token.scopes = scope.split(' ')
        }
      } else if (account?.scope) {
        token.scopes = account.scope.split(' ')
      }

      return token
    },
    async session({ session, token }) {
      // Transfer the access token and scopes to the session
      session.accessToken = token.accessToken as string
      session.idToken = token.idToken as string
      session.scopes = token.scopes as string[] | undefined
      return session
    },
  },
})
