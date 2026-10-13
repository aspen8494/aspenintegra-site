import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

/**
 * Research projects — featured work with problem → approach → result narrative.
 * Add a project by dropping a new .md file into src/content/research/.
 */
const research = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/research' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    tags: z.array(z.string()).default([]),
    repo: z.string().url().optional(),
    repoLabel: z.string().optional(),
    /** Higher = shown first on the Research page */
    weight: z.number().default(0),
    status: z.enum(['active', 'complete', 'archived']).default('active'),
  }),
});

/**
 * Blog posts. Add a post by dropping a new .md file into src/content/blog/.
 * Filename becomes the URL slug.
 */
const blog = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/blog' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    tags: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
  }),
});

export const collections = { research, blog };
