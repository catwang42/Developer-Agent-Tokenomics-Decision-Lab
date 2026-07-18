/*
 * SYNTHETIC hidden-test fixture — NOT a real sealed test.
 *
 * Purpose: exercise the hidden-gate machinery (load -> hash -> inject -> run ->
 * record) end-to-end so the 10-point validator can be demonstrated at a full
 * 10/10 without the human-held sealed tests. It is a fixture (tests/fixtures/,
 * SYNTHETIC in name and body per CLAUDE.md rule 1) and must NEVER live under
 * tasks/hidden/ or results/. The real sealed hidden test is authored by a human
 * (tasks/hidden/README-FOR-HUMAN.md).
 *
 * Like the public repro, the discriminating assertion is on the arguments passed
 * to the data layer, because the deep Prisma mock returns its value verbatim and
 * cannot observe a wrong `select` via the return value.
 */
import prismaMock from '../prisma-mock';
import { getCurrentUser } from '../../app/routes/auth/auth.service';

describe('getCurrentUser — SYNTHETIC hidden acceptance', () => {
  test('selects id and carries it into the returned profile', async () => {
    const mockedResponse = {
      id: 7,
      username: 'RealWorld',
      email: 'realworld@me',
      password: 'hashed',
      bio: null,
      image: null,
      token: '',
      demo: false,
    };
    // @ts-ignore - mock returns this verbatim, ignoring the select clause
    prismaMock.user.findUnique.mockResolvedValue(mockedResponse);

    const result = await getCurrentUser(7);

    const call = prismaMock.user.findUnique.mock.calls[0][0] as {
      select?: Record<string, unknown>;
    };
    expect(call.select).toHaveProperty('id', true);
    expect(result).toHaveProperty('id', 7);
    expect(result).toHaveProperty('token');
  });
});
