/*
 * PUBLIC feature-spec test for the pilot task (pilot-realworld-draft-articles).
 *
 * Feature: articles can be created as drafts (a `draft` boolean, default false),
 * and draft articles are excluded from the public article list so only non-draft
 * articles surface in GET /articles.
 *
 * Standard feature pre-modification failure (SPEC 2.8): on the unmodified repo the
 * `draft` field/behaviour does not exist yet, so these assertions fail. On the
 * canonical solution they pass.
 *
 * As with the rest of the suite, the deep Prisma mock returns its value verbatim
 * and ignores the `data`/`where` clauses, so the faithful DB-free signal is what
 * the service passes to the data layer. Args are read untyped so the test compiles
 * on the unmodified repo and fails at runtime (not at compile time).
 *
 * Import order matters: prisma-mock before the service.
 */
import prismaMock from '../prisma-mock';
import { createArticle, getArticles } from '../../app/routes/article/article.service';

const articleRow = (over: Record<string, unknown> = {}) => ({
  id: 1,
  authorId: 1,
  slug: 'how-to-1',
  title: 'How to',
  description: 'desc',
  body: 'body',
  draft: false,
  createdAt: new Date(),
  updatedAt: new Date(),
  tagList: [],
  favoritedBy: [],
  author: { username: 'RealWorld', bio: null, image: null, followedBy: [] },
  ...over,
});

describe('Draft articles — feature spec', () => {
  test('createArticle persists the draft flag to the data layer', async () => {
    // @ts-ignore - no existing article with this slug
    prismaMock.article.findUnique.mockResolvedValue(null);
    // @ts-ignore - mock returns this verbatim, ignoring the data clause
    prismaMock.article.create.mockResolvedValue(articleRow({ draft: true }));

    await createArticle(
      { title: 'How to', description: 'desc', body: 'body', draft: true },
      1,
    );

    const call = prismaMock.article.create.mock.calls[0][0] as {
      data?: Record<string, unknown>;
    };
    expect(call.data).toBeDefined();
    expect(call.data).toHaveProperty('draft', true);
  });

  test('getArticles excludes drafts from the public list', async () => {
    // @ts-ignore
    prismaMock.article.count.mockResolvedValue(0);
    // @ts-ignore
    prismaMock.article.findMany.mockResolvedValue([]);

    await getArticles({}, undefined);

    const call = prismaMock.article.findMany.mock.calls[0][0] as {
      where?: { AND?: Array<Record<string, unknown>> };
    };
    const and = call.where?.AND ?? [];
    expect(and).toEqual(
      expect.arrayContaining([expect.objectContaining({ draft: false })]),
    );
  });
});
