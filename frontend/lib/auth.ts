import { logoutUser } from '@/app/lib/api';

/**
 * Perform complete client & backend auth state cleanup and redirect to login page.
 */
export async function logout(router?: { push: (url: string) => void }) {
  try {
    await logoutUser();
  } catch {
    // ignore
  }

  if (typeof window !== 'undefined') {
    localStorage.removeItem('agrosphere_token');
    sessionStorage.clear();
  }

  if (router) {
    router.push('/login');
  } else if (typeof window !== 'undefined') {
    window.location.href = '/login';
  }
}
