import clsx from 'clsx';

// Decorative: it always sits beside the service's name, so it carries no alt text.
export function BrandMark({ className }: { className?: string }) {
  return (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/fds-mark.svg" alt="" className={clsx('logo-default', className)} />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/fds-mark-reversed.svg" alt="" className={clsx('logo-reversed', className)} />
    </>
  );
}
