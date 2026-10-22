# Notes Claude writes with hub_note (decisions, bugs, notes, snippets,
# architecture, open points) and the project note every project hangs on.
# The same title replaces a note; architecture and open points collect one
# section per title in a single note per project.
import os
import re

from . import i18n, projects, search, store, system, text, vault


def project_note(project):
    # 01_Projects/<p>/<p>.md - the project's centre in the Obsidian graph
    name = text.file_name(project)
    path = os.path.join(vault.PROJECTS, name, name + '.md')
    if not os.path.exists(path):
        lang = vault.lang()
        root = projects.root_of(project)
        head = {'kind': 'project', 'created': vault.now()}
        if root:
            head['root'] = system.tilde(root)
        lines = [vault.front_text(head), f'# {project}', '']
        if root:
            lines += [i18n.t('note.project_map', lang, project=project, root=system.tilde(root)), '']
        lines += [i18n.t('note.project_links', lang), '']
        vault.write(path, '\n'.join(lines))
    return path


def save(project, title, content, kind='note', tags=(), source='claude'):
    # -> path relative to the vault. The same title replaces the note.
    kind = vault.KINDS.get(str(kind).lower(), 'note')
    project = projects.name(project) or (str(project).strip() or vault.general())
    title = text.short(title, 90)
    tags = [re.sub(r'[^\w/-]+', '-', str(x)).strip('-') for x in (tags or []) if str(x).strip()]
    project_note(project)
    folder = os.path.join(vault.PROJECTS, text.file_name(project))
    if kind == 'snippet':
        path = os.path.join(vault.LIBRARY, text.file_name(title) + '.md')
    elif kind in vault.COLLECTED:
        path = os.path.join(folder, f'{text.file_name(project)} {vault.layout(kind)}.md')
    else:
        path = os.path.join(folder, vault.layout(kind), text.file_name(title) + '.md')
    link = f'{i18n.t("note.project", vault.lang())}: [[{project}]]'
    with vault.lock('note'):
        old_head, old_body = vault.front(vault.read(path))
        head = {'project': project, 'kind': kind}
        if tags or old_head.get('tags'):
            head['tags'] = tags or old_head.get('tags')
        head['created'] = old_head.get('created') or vault.now()
        head['modified'] = vault.now()
        head['source'] = source
        if kind in vault.COLLECTED:
            body = set_section(old_body or f'# {project} {vault.layout(kind)}\n\n{link}\n', title, content.strip())
        else:
            body = f'# {title}\n\n{link}\n\n{content.strip()}\n'
        vault.write(path, vault.front_text(head) + body)
    rel = vault.rel(path)
    try:
        with store.transaction() as c:
            search.index_note(c, rel)
    except store.NoIndex:
        pass
    return rel


def set_section(body, title, content):
    # replace "## title" or append it
    parts = re.split(r'(?m)^(?=## )', body)
    new = f'## {title}\n{content}\n\n'
    for i, part in enumerate(parts):
        if part.startswith('## ') and part[3:].split('\n', 1)[0].strip() == title:
            parts[i] = new
            return ''.join(parts).rstrip() + '\n'
    return body.rstrip() + '\n\n' + new.rstrip() + '\n'
