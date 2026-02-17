"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import { User, LogOut, Loader2, Users } from "lucide-react";
import { getUserRole, getRoleColor, getRoleBgColor } from "@/lib/roles";
import { useEffect } from "react";

export function UserMenu() {
  const { data: session, status } = useSession();

  // Handle "Switch Account" flow:
  // 1. If we see ?switch_account=true, it means we just logged out from Keycloak.
  // 2. We immediately trigger signIn() to go back to Keycloak login (which will now be a clean form).
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("switch_account") === "true") {
        // Clean up the URL
        const newUrl = window.location.pathname;
        window.history.replaceState({}, "", newUrl);
        // Trigger fresh login
        signIn("keycloak");
      }
    }
  }, []);

  const handleSwitchAccount = async () => {
    // To get a "completely clear form", we must first logout from Keycloak to kill the session.
    // Flow: App -> Keycloak Logout -> App(?switch_account=true) -> Keycloak Login (Clean)

    const keycloakUrl = process.env.NEXT_PUBLIC_KEYCLOAK_URL || "http://localhost:8080";
    const realm = "fds";
    // Redirect back to the app with a flag to trigger immediate login
    const switchRedirectUri = encodeURIComponent(`${window.location.origin}/?switch_account=true`);

    // Construct Logout URL (Keycloak 18+ style)
    let logoutUrl = `${keycloakUrl}/realms/${realm}/protocol/openid-connect/logout?post_logout_redirect_uri=${switchRedirectUri}`;

    // Add id_token_hint if available (prevents "Confirm Logout" screen)
    if (session?.idToken) {
      logoutUrl += `&id_token_hint=${session.idToken}`;
    }

    // Sign out locally first to clear NextAuth state
    await signOut({ redirect: false });

    // Redirect to Keycloak to finish the job
    window.location.href = logoutUrl;
  };

  if (status === "loading") {
    return <Loader2 className="w-4 h-4 animate-spin text-slate-500" />;
  }

  if (status === "authenticated" && session?.user) {
    const role = getUserRole(session.scopes);
    const roleColor = getRoleColor(role);
    // Use the helper, or fallback if not imported yet (though it is)
    const roleBg = getRoleBgColor ? getRoleBgColor(role) : "bg-slate-800";

    return (
      <div className="flex items-center justify-end gap-4 ml-auto">
        <div className="flex items-center gap-2 justify-end">
          <div className={`${roleBg} p-2 rounded-full transition-colors shrink-0`}>
            <User className={`w-4 h-4 ${roleColor}`} />
          </div>
          <div className={`text-sm font-medium ${roleColor} leading-tight text-left`}>
            {role}
          </div>
        </div>

        <div className="flex flex-col-reverse md:flex-row items-end md:items-center gap-1 md:gap-2 border-l border-slate-700 pl-4">
          <button
            onClick={handleSwitchAccount}
            className="text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1"
            title="Switch Account"
          >
            <Users className="w-3 h-3" />
            Switch
          </button>

          <button
            onClick={() => signOut()}
            className="text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1 whitespace-nowrap"
            title="Sign Out"
          >
            <LogOut className="w-3 h-3" />
            Sign Out
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={() => signIn("keycloak")}
      className="text-sm font-medium text-primary hover:text-blue-400 transition-colors"
    >
      Sign In
    </button>
  );
}
