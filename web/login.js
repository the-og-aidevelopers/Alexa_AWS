const form = document.getElementById('auth-form');
const message = document.getElementById('message');
async function submit(action) {
  const buttons = [...form.querySelectorAll('button')];
  if (buttons.some(button => button.disabled)) return;
  if (!form.reportValidity()) return;
  buttons.forEach(button => { button.disabled = true; });
  message.textContent = 'Please wait…';
  try {
    const response = await fetch(`/api/auth/${action}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error);
    location.assign('/');
  } catch (error) {
    message.textContent = error.message || 'Unable to sign in.';
  } finally { buttons.forEach(button => { button.disabled = false; }); }
}
form.addEventListener('submit', event => { event.preventDefault(); submit('login'); });
document.getElementById('register').addEventListener('click', () => submit('register'));
fetch('/api/auth/session').then(response => response.json()).then(body => {
  if (body.authenticated) location.replace('/');
  if (body.provider !== 'local') {
    form.hidden = true;
    document.getElementById('provider-note').textContent = 'This deployment uses an external identity provider. Use its authenticated client. Local password login is disabled.';
  }
}).catch(() => { message.textContent = 'Unable to reach the server.'; });
