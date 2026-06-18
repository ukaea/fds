/**
 * Role hierarchy and utility functions for determining user privileges
 * Based on backend security scopes
 */

export type UserRole = 'Admin' | 'Device Admin' | 'Shot Operator' | 'Viewer';

/**
 * Determines the highest role/privilege level for a user based on their scopes
 *
 * Hierarchy (highest to lowest):
 * 1. Admin - has 'fds-admin' scope (global admin, full access)
 * 2. Device Admin - has '{device_name}_admin' scope (admin for specific devices)
 * 3. Shot Operator - has 'shot-operator:{device_name}' scope (can operate shots)
 * 4. Viewer - default for authenticated users (read-only)
 */
export function getUserRole(scopes: string[] | undefined): UserRole {
  if (!scopes || scopes.length === 0) {
    return 'Viewer';
  }

  // Check for global admin
  if (scopes.includes('fds-admin')) {
    return 'Admin';
  }

  // Check for device admin (pattern: {device_name}_admin)
  const hasDeviceAdmin = scopes.some(scope => scope.endsWith('_admin'));
  if (hasDeviceAdmin) {
    return 'Device Admin';
  }

  // Check for shot operator (pattern: shot-operator:{device_name})
  const hasShotOperator = scopes.some(scope => scope.startsWith('shot-operator:'));
  if (hasShotOperator) {
    return 'Shot Operator';
  }

  return 'Viewer';
}

/**
 * Gets the CSS class for styling based on role
 */
export function getRoleColor(role: UserRole): string {
  switch (role) {
    case 'Admin':
      return 'text-destructive font-bold'; // Distinctive Red for Admin
    case 'Device Admin':
      return 'text-foreground font-semibold';
    case 'Shot Operator':
      return 'text-muted-foreground';
    case 'Viewer':
      return 'text-muted-foreground';
  }
}

export function getRoleBgColor(role: UserRole): string {
  switch (role) {
    case 'Admin':
      return 'bg-muted';
    case 'Device Admin':
      return 'bg-muted';
    case 'Shot Operator':
      return 'bg-muted';
    case 'Viewer':
      return 'bg-muted';
  }
}
