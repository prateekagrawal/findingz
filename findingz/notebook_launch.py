"""Small first-party Streamlit component: user-click popup, then save-before-navigation."""
import streamlit as st

JS = """
// Preserve only our own pending tab handles across component script reloads.
const pendingKey = Symbol.for('findingz.notebookLaunch.pending');
const pending = window[pendingKey] || (window[pendingKey] = new Map());
export default function(component) {
    const {data, parentElement, setTriggerValue} = component;
    const status = parentElement.querySelector('[role="status"]');
    const buttons = [...parentElement.querySelectorAll('button')];
    const reply = data.reply;
    if (reply && pending.has(reply.id)) {
        const popup = pending.get(reply.id);
        pending.delete(reply.id);
        if (reply.error) {
            if (popup && !popup.closed) popup.close();
            status.textContent = reply.error;
        } else if (popup && !popup.closed && reply.url) {
            popup.opener = null;
            popup.location.replace(reply.url);
            status.textContent = 'Notebook saved and opened in JupyterLab.';
        } else {
            status.textContent = 'Notebook saved. Use the saved path or recovery link below.';
        }
    }
    buttons.forEach(button => {
        button.disabled = pending.size > 0 || (button.dataset.mode === 'current' && !data.enabled);
        button.onclick = () => {
            const id = crypto.randomUUID();
            // Open synchronously during the user gesture, not after a server round trip.
            const popup = data.can_open ? window.open('about:blank', '_blank') : null;
            if (popup) popup.document.body.textContent = 'Saving your analysis notebook…';
            pending.set(id, popup);
            buttons.forEach(item => item.disabled = true);
            status.textContent = data.can_open && !popup
                ? 'Your browser blocked the tab. Saving the notebook; a recovery link will appear below.'
                : 'Saving notebook…';
            setTriggerValue('request', {id, mode: button.dataset.mode});
        };
    });
}
"""
launch_buttons = st.components.v2.component(
    "findingz_notebook_launch",
    html='<div class="actions"><button data-mode="current">Continue current analysis in Jupyter</button>'
         '<button data-mode="blank">Start from blank template</button></div><p role="status"></p>',
    css="""
    .actions {display:flex; gap:1rem; flex-wrap:wrap}
    button {font:inherit; color:var(--st-text-color); background:var(--st-background-color);
      border:1px solid var(--st-border-color, #888); border-radius:.5rem; padding:.5rem .8rem; cursor:pointer}
    button:hover {border-color:var(--st-primary-color)}
    button:disabled {opacity:.5; cursor:default}
    p {font:inherit; font-size:.875rem}
    """,
    js=JS,
)
