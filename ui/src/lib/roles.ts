/**
 * The label the user menu shows for a signed-in user.
 *
 * FDS defines one role, 'fds-admin'. Every other role is a name the identity
 * provider issues and records list in their read_roles and write_roles, so a
 * token alone cannot say what else the user may do.
 */

export type UserRole = 'Admin' | 'Viewer';

export function getUserRole(roles: string[] | undefined): UserRole {
  return roles?.includes('fds-admin') ? 'Admin' : 'Viewer';
}

/**
 * Gets the CSS class for styling based on role
 */
export function getRoleColor(role: UserRole): string {
  return role === 'Admin' ? 'text-brand-text font-bold' : 'text-primary';
}

export function getRoleBgColor(role: UserRole): string {
  return role === 'Admin' ? 'bg-brand/15' : 'bg-muted';
}
