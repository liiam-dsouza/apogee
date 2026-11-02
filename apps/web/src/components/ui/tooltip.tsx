import { Popover as PopoverPrimitive, Tooltip as TooltipPrimitive } from 'radix-ui'
import type { ComponentProps, ReactNode } from 'react'
import { useNoHover } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'

export const TooltipProvider = TooltipPrimitive.Provider

const contentClass =
  'z-50 max-w-72 rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-foreground shadow-lg'

/**
 * Nothing hovers on a phone, so a tooltip never shows there. Pass `tappable`
 * when the content is information (not just a button's name): on touch
 * screens it then opens on tap, as a popover.
 */
export function Tooltip({
  content,
  side = 'top',
  children,
  className,
  tappable = false,
}: {
  content: ReactNode
  side?: ComponentProps<typeof TooltipPrimitive.Content>['side']
  children: ReactNode
  className?: string
  tappable?: boolean
}) {
  const noHover = useNoHover()
  if (tappable && noHover) {
    return (
      <PopoverPrimitive.Root>
        <PopoverPrimitive.Trigger asChild>{children}</PopoverPrimitive.Trigger>
        <PopoverPrimitive.Portal>
          <PopoverPrimitive.Content
            side={side}
            sideOffset={8}
            collisionPadding={8}
            className={cn(contentClass, className, 'max-w-[calc(100vw-1rem)]')}
          >
            {content}
          </PopoverPrimitive.Content>
        </PopoverPrimitive.Portal>
      </PopoverPrimitive.Root>
    )
  }
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content side={side} sideOffset={8} className={cn(contentClass, className)}>
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}
