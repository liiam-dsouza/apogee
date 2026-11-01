import { Tooltip as TooltipPrimitive } from 'radix-ui'
import type { ComponentProps, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export const TooltipProvider = TooltipPrimitive.Provider

export function Tooltip({
  content,
  side = 'top',
  children,
  className,
}: {
  content: ReactNode
  side?: ComponentProps<typeof TooltipPrimitive.Content>['side']
  children: ReactNode
  className?: string
}) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={8}
          className={cn(
            'z-50 max-w-72 rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-foreground shadow-lg',
            className,
          )}
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}
