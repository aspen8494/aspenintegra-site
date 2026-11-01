/**
 * Central site configuration — edit these values to update the whole site.
 */
export const SITE = {
  /** Used in <title>, meta tags, and RSS */
  title: 'Aspen Integra',
  tagline: 'Personal Research Laboratory',
  description:
    'Open-source nuclear waste research: Hanford tank waste databases, Best-Basis Inventory data, machine-learning mission models, interactive public dashboards, and free white papers on vitrification and tank-farm mission planning.',
  author: 'Aspen',
  /** Contact + social */
  email: 'info@aspenintegra.com',
  github: 'https://github.com/aspen8494',
  githubUser: 'aspen8494',
  linkedin: 'https://www.linkedin.com/in/adam-spencer-538739101',
  location: 'Richland, WA',
} as const;

export const NAV = [
  { href: '/research/', label: 'Research' },
  { href: '/papers/', label: 'Papers' },
  { href: '/data/', label: 'Open Data' },
  { href: '/playground/', label: 'Playground' },
  { href: '/blog/', label: 'Blog' },
  { href: '/about/', label: 'About' },
  { href: '/contact/', label: 'Contact' },
] as const;
