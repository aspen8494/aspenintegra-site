/**
 * Central site configuration — edit these values to update the whole site.
 */
export const SITE = {
  /** Used in <title>, meta tags, and RSS */
  title: 'Aspen Integra',
  tagline: 'Personal Research Laboratory',
  description:
    'Personal research laboratory of Aspen, a nuclear process engineer. Research write-ups, a blog, and a CV linking machine learning with waste disposal, treatment, and power.',
  author: 'Aspen',
  /** Contact + social */
  email: 'aspen.ws.anon@proton.me',
  github: 'https://github.com/aspen8494',
  githubUser: 'aspen8494',
  linkedin: 'https://www.linkedin.com/in/adam-spencer-538739101',
  location: 'Richland, WA',
} as const;

export const NAV = [
  { href: '/', label: 'Home' },
  { href: '/research/', label: 'Research' },
  { href: '/papers/', label: 'White Paper' },
  { href: '/blog/', label: 'Blog' },
  { href: '/about/', label: 'About' },
  { href: '/cv/', label: 'CV' },
  { href: '/playground/', label: 'Playground' },
  { href: '/contact/', label: 'Contact' },
] as const;
