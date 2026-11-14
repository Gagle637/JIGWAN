import type { ComponentProps } from 'react';

import { cn } from '@/lib/cn';

type ButtonVariant = 'primary' | 'ghost';
type ButtonSize = 'sm' | 'md';

interface ButtonProps extends ComponentProps<'button'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
  ghost: 'text-foreground-muted hover:bg-surface-muted',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
};

export function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn('rounded-md font-medium', variantClasses[variant], sizeClasses[size], className)}
      {...props}
    />
  );
}
