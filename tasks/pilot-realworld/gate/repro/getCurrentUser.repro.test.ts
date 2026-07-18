/*
 * PUBLIC repro test for the pilot task (pilot-realworld-missing-user-id).
 *
 * The bug: getCurrentUser() selects the user's fields from the data layer but
 * omits `id`, so the returned profile has no id and the JWT is signed with an
 * undefined id. The canonical fix adds `id: true` to the Prisma `select`.
 *
 * Why this test asserts on the *arguments* to findUnique, not the return value:
 * the suite uses a deep Prisma mock (src/tests/prisma-mock.ts) whose
 * mockResolvedValue is returned verbatim regardless of the `select` clause. The
 * mock therefore cannot observe a wrong `select` via its return value — the only
 * faithful, DB-free signal of the defect is what the service *asked the data
 * layer for*. This test fails at the pinned commit (no `id` in select) and
 * passes on the canonical solution.
 *
 * Import order matters: prisma-mock must be imported BEFORE the service so the
 * jest.mock registration is in place when auth.service loads prisma-client.
 */
import prismaMock from '../prisma-mock';
import { getCurrentUser } from '../../app/routes/auth/auth.service';

describe('getCurrentUser — missing user id repro', () => {
  test('requests the user id from the data layer', async () => {
    const mockedResponse = {
      id: 123,
      username: 'RealWorld',
      email: 'realworld@me',
      password: 'hashed',
      bio: null,
      image: null,
      token: '',
      demo: false,
    };
    // @ts-ignore - the mock returns this verbatim, ignoring the select clause
    prismaMock.user.findUnique.mockResolvedValue(mockedResponse);

    await getCurrentUser(123);

    expect(prismaMock.user.findUnique).toHaveBeenCalledTimes(1);
    const call = prismaMock.user.findUnique.mock.calls[0][0] as {
      select?: Record<string, unknown>;
    };
    // The discriminating assertion: the service must select `id`.
    expect(call.select).toBeDefined();
    expect(call.select).toHaveProperty('id', true);
  });
});
