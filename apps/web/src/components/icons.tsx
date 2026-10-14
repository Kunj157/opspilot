import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    >
      {children}
    </svg>
  );
}

export const icons = {
  overview: (p: IconProps) => (
    <Icon {...p}>
      <rect x="2" y="2" width="5" height="5" rx="1" />
      <rect x="9" y="2" width="5" height="5" rx="1" />
      <rect x="2" y="9" width="5" height="5" rx="1" />
      <rect x="9" y="9" width="5" height="5" rx="1" />
    </Icon>
  ),
  incidents: (p: IconProps) => (
    <Icon {...p}>
      <path d="M8 1.8 14.6 13.5H1.4L8 1.8Z" />
      <path d="M8 6.5v3M8 11.6v.1" />
    </Icon>
  ),
  services: (p: IconProps) => (
    <Icon {...p}>
      <circle cx="4" cy="4" r="2" />
      <circle cx="12" cy="4" r="2" />
      <circle cx="8" cy="12" r="2" />
      <path d="M5.4 5.4 7 10.4M10.6 5.4 9 10.4M6 4h4" />
    </Icon>
  ),
  models: (p: IconProps) => (
    <Icon {...p}>
      <path d="M1.5 14.5h13" />
      <path d="M3.5 12V8.5M7 12V4M10.5 12V6.5M14 12V2.5" />
    </Icon>
  ),
  status: (p: IconProps) => (
    <Icon {...p}>
      <path d="M1.5 8h3l2-4.5 3 9 2-4.5h3" />
    </Icon>
  ),
  audit: (p: IconProps) => (
    <Icon {...p}>
      <path d="M4 1.5h6l3 3v10H4z" />
      <path d="M6.5 7.5h4M6.5 10h4M10 1.5v3h3" />
    </Icon>
  ),
  menu: (p: IconProps) => (
    <Icon {...p}>
      <path d="M2.5 4h11M2.5 8h11M2.5 12h11" />
    </Icon>
  ),
  runbooks: (p: IconProps) => (
    <Icon {...p}>
      <path d="M3 2.5h7.5a2 2 0 0 1 2 2v9H5a2 2 0 0 1-2-2v-9Z" />
      <path d="M3 11.5a2 2 0 0 1 2-2h7.5M6 5.5h4" />
    </Icon>
  ),
  chevron: (p: IconProps) => (
    <Icon {...p}>
      <path d="m4.5 6.5 3.5 3.5 3.5-3.5" />
    </Icon>
  ),
  sort: (p: IconProps) => (
    <Icon {...p}>
      <path d="M8 3v10M4.5 9.5 8 13l3.5-3.5" />
    </Icon>
  ),
  search: (p: IconProps) => (
    <Icon {...p}>
      <circle cx="7" cy="7" r="4.5" />
      <path d="m10.5 10.5 3 3" />
    </Icon>
  ),
  close: (p: IconProps) => (
    <Icon {...p}>
      <path d="m4 4 8 8m0-8-8 8" />
    </Icon>
  ),
};

export type IconName = keyof typeof icons;
