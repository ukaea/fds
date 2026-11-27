/**
 * How the user menu shows a signed-in user's roles.
 *
 * FDS defines one role, 'fds-admin'. Every other role is a name the identity
 * provider issues and records list in their read_roles and write_roles, so the
 * menu lists the roles the token carries rather than naming a kind of user.
 */

export function holdsAdmin(roles: string[] | undefined): boolean {
  return roles?.includes('fds-admin') ?? false;
}

export function describeRoles(roles: string[] | undefined): string {
  return roles?.length ? [...roles].sort().join(', ') : 'no roles';
}

/**
 * Gets the CSS class for styling, by whether the user holds fds-admin
 */
export function getRoleColor(admin: boolean): string {
  return admin ? 'text-brand-text font-bold' : 'text-primary';
}

export function getRoleBgColor(admin: boolean): string {
  return admin ? 'bg-brand/15' : 'bg-muted';
}
