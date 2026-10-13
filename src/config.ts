/**
 * Central site configuration — edit these values to update the whole site.
 */
export const SITE = {
  /** Used in <title>, meta tags, and RSS */
  title: 'Aspen Integra',
  tagline: 'Personal Research Laboratory',
  description:
    'Aspen Integra is a personal research laboratory linking the growing AI industry and infrastructure with areas that enhance nuclear waste disposal, treatment, and power. Research projects, engineering write-ups, and a CV by Aspen Spencer.',
  author: 'Aspen',
  /** Contact + social */
  email: 'aspencer8119@gmail.com',
  github: 'https://github.com/aspen8494',
  githubUser: 'aspen8494',
  linkedin: 'https://www.linkedin.com/in/adam-spencer-538739101',
  location: 'Richland, WA',
} as const;

export const NAV = [
  { href: '/', label: 'Home' },
  { href: '/research/', label: 'Research' },
  { href: '/blog/', label: 'Blog' },
  { href: '/about/', label: 'About' },
  { href: '/cv/', label: 'CV' },
  { href: '/playground/', label: 'Playground' },
  { href: '/contact/', label: 'Contact' },
] as const;
