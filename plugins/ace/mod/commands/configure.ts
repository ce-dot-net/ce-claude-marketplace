import { type Cmd, type Kit, confirm } from './kit.ts'
import { fixGitignore, gitignoreDiff } from '../context/index.ts'
import { projectList, suggest } from '../handlers/context.ts'
import { run } from '../io/fs.ts'
// Bind this repo: writes the tracked .ace/config.json at the MAIN checkout root (never settings.json, never a token);
// shows the .gitignore diff when the file is ignored. Everything only after the button.
export const configure: Cmd = { name: 'configure', md: 'ace-configure', description: 'Bind this repo to an ACE project (preview + confirm)', argumentHint: '[prj_... | org_... prj_...]' }
export async function configureCmd($: any, { c, args }: Kit): Promise<string> {
    const cc: any = c
    const main = c.mainRoot ?? c.gitRoot
    const projects = await projectList($, c)
    const want = args.trim().split(/\s+/).filter(Boolean)
    const now = cc.bound ? `Now: ${cc.projectId} (org ${cc.orgId}) via ${cc.source}${cc.path ? ` · ${cc.path}` : ''}` : `Now: not bound (${cc.reason})`
    if (!want.length) {
      const s = suggest(projects, c.root)
      const list = projects.slice(0, 50).map(p => `- ${p.name}  ${p.projectId}  (org ${p.orgId})`).join('\n')
      if (s && main) await confirmBind($, main, s.orgId, s.projectId, s.name)
      return [now, main ? `Binding file: ${main}/.ace/config.json` : 'Not a git repo: bind with ACE_ORG_ID/ACE_PROJECT_ID instead.',
        s ? `Suggestion by name: ${s.name} (${s.projectId}) — [Verbinden] above the prompt` : 'No project matches the repo name.',
        list ? `\nProjects:\n${list}\n\n/ace:ace-configure <prj_...> binds one of them.` : ''].join('\n')
    }
    if (!main) return 'Not a git repo: there is no tracked file to write. Set ACE_ORG_ID / ACE_PROJECT_ID in the env instead.'
    const prj = want.find(w => w.startsWith('prj_')), org = want.find(w => w.startsWith('org_')) ?? projects.find(p => p.projectId === prj)?.orgId
    if (!prj || !org) return 'Usage: /ace:ace-configure [org_...] prj_...  (the project must be in /ace:ace-configure\'s list, or give the org)'
    return confirmBind($, main, org, prj, projects.find(p => p.projectId === prj)?.name ?? prj)
}
export async function confirmBind($: any, main: string, orgId: string, projectId: string, name: string) {
  let gi = ''
  if ((await run($, ['git', '-C', main, 'check-ignore', '-q', '.ace/config.json']))?.exitCode === 0) {
    let before = ''
    try { before = await $.fs.read(`${main}/.gitignore`) } catch { /* none */ }
    gi = `\n.gitignore ignores it; this change makes it trackable:\n${gitignoreDiff(before, fixGitignore(before).text)}`
  }
  return confirm($, { label: `Verbinden: ${name}`, kind: 'bind', orgId, projectId,
    preview: `Writes ${main}/.ace/config.json:\n${JSON.stringify({ orgId, projectId }, null, 2)}${gi}\nNothing is staged or committed; commit it to bind every clone.` })
}
