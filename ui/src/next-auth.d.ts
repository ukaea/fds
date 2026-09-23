import { DefaultSession } from "next-auth"

declare module "next-auth" {
  interface Session {
    accessToken?: string
    user: {
      /** The user's postal address. */
      address: string
    } & DefaultSession["user"]
  }
}
