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

      // The login service puts the user's FDS roles in the ID token's roles claim
      if (profile && Array.isArray(profile.roles)) {
        token.roles = profile.roles as string[]
      }

      return token
    },
    async session({ session, token }) {
      // Transfer the access token and roles to the session
      session.accessToken = token.accessToken as string
      session.idToken = token.idToken as string
      session.roles = token.roles as string[] | undefined
      return session
    },
  },
})
