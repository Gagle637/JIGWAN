import type { ComponentProps } from 'react';

import { cn } from '@/lib/cn';

interface CardProps extends ComponentProps<'div'> {
  title?: string;
}

export function Card({ title, className, children, ...props }: CardProps) {
  return (
    <div className={cn('rounded-md border border-border bg-surface p-4', className)} {...props}>
      {title && <h3 className="mb-2 text-sm font-semibold text-foreground">{title}</h3>}
      {children}
    </div>
  );
}
