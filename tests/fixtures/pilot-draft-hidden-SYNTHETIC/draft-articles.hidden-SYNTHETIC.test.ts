/*
 * SYNTHETIC hidden-test fixture for the Draft-articles pilot — NOT a real sealed
 * test. It exercises the hidden-gate machinery (load -> hash -> inject -> run ->
 * record) so the 10-point validator can be demonstrated at a full 10/10 without
 * the human-held sealed tests. Fixture only (tests/fixtures/, SYNTHETIC in name
 * and body per CLAUDE.md rule 1); must NEVER live under any task's hidden
 * directory or under results/. The real sealed tests are authored by a human
 * (tasks/pilot-realworld/hidden/README-FOR-HUMAN.md).
 */
import prismaMock from '../prisma-mock';
import { createArticle, getArticles } from '../../app/routes/article/article.service';

describe('Draft articles — SYNTHETIC hidden acceptance', () => {
  test('create persists draft and list filters drafts', async () => {
    // @ts-ignore
    prismaMock.article.findUnique.mockResolvedValue(null);
    // @ts-ignore
    prismaMock.article.create.mockResolvedValue({
      id: 1, authorId: 1, slug: 's', title: 't', description: 'd', body: 'b',
      draft: true, createdAt: new Date(), updatedAt: new Date(),
      tagList: [], favoritedBy: [],
      author: { username: 'u', bio: null, image: null, followedBy: [] },
    });

    await createArticle(
      { title: 't', description: 'd', body: 'b', draft: true }, 1,
    );
    const createCall = prismaMock.article.create.mock.calls[0][0] as {
      data?: Record<string, unknown>;
    };
    expect(createCall.data).toHaveProperty('draft', true);

    // @ts-ignore
    prismaMock.article.count.mockResolvedValue(0);
    // @ts-ignore
    prismaMock.article.findMany.mockResolvedValue([]);
    await getArticles({}, undefined);
    const listCall = prismaMock.article.findMany.mock.calls[0][0] as {
      where?: { AND?: Array<Record<string, unknown>> };
    };
    expect(listCall.where?.AND ?? []).toEqual(
      expect.arrayContaining([expect.objectContaining({ draft: false })]),
    );
  });
});
