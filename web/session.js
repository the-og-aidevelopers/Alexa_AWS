(async () => {
  const bar = document.getElementById('account');
  if (!bar) return;
  try {
    const response = await fetch('/api/auth/session', { cache: 'no-store' });
    const session = await response.json();
    if (!session.authenticated) { location.replace('/login'); return; }
    const name = document.createElement('span');
    name.textContent = session.identity.household_name;
    bar.append(name);
    if (session.provider === 'local') {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = 'Sign out';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          const response = await fetch('/api/auth/logout', { method: 'POST' });
          if (!response.ok) throw new Error('Sign out failed');
          location.replace('/login');
        } catch { button.disabled = false; button.textContent = 'Retry sign out'; }
      });
      bar.append(button);
    }
  } catch { bar.textContent = 'Session unavailable — reload to retry.'; }
})();
