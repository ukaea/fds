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

  // Signing out here alone leaves the session at the provider, and the next
  // sign-in goes straight back in without a login form. So both buttons end
  // that session too: App -> provider logout -> returnTo.
  const endSession = async (returnTo: string) => {
    const config = await fetch('/api/auth-config')
      .then((response) => response.json() as Promise<{ logoutEndpoint: string | null }>)
      .catch(() => ({ logoutEndpoint: null }));

    if (!config.logoutEndpoint) {
      await signOut();
      return;
    }

    const logoutUrl = new URL(config.logoutEndpoint);
    logoutUrl.searchParams.set("post_logout_redirect_uri", returnTo);
    // Without the hint the provider asks the user to confirm the logout.
    if (session?.idToken) {
      logoutUrl.searchParams.set("id_token_hint", session.idToken);
    }

    await signOut({ redirect: false });
    window.location.assign(logoutUrl.toString());
  };

  const handleSwitchAccount = () =>
    endSession(`${window.location.origin}/?switch_account=true`);

  const handleSignOut = () => endSession(`${window.location.origin}/`);

  if (status === "loading") {
    return <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />;
  }

  if (status === "authenticated" && session?.user) {
    const role = getUserRole(session.roles);
    const roleColor = getRoleColor(role);
    const roleBg = getRoleBgColor(role);

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

        <div className="flex flex-col-reverse md:flex-row items-end md:items-center gap-1 md:gap-2 border-l border-border pl-4">
          <button
            onClick={handleSwitchAccount}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
            title="Switch Account"
          >
            <Users className="w-3 h-3" />
            Switch
          </button>

          <button
            onClick={handleSignOut}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1 whitespace-nowrap"
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
      className="text-sm font-medium text-primary hover:text-foreground transition-colors"
    >
      Sign In
    </button>
  );
}
