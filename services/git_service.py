import subprocess
from datetime import datetime

from utils import log_to_file


class GitUpdateService:
    """
    Dịch vụ quản lý cập nhật code từ GitHub
    - Pull latest code từ remote
    - Reload cogs tự động
    - Kiểm tra trạng thái git
    """
    
    def __init__(self, repo_path='.'):
        self.repo_path = repo_path
        self.log_prefix = "[GIT_SERVICE]"

    RUNTIME_PATH_PREFIXES = (
        "database/",
        "logs/",
        "__pycache__/",
        ".venv/",
        "venv/",
    )
    
    def _run_git_command(self, command):
        """Chạy lệnh git và trả về kết quả"""
        try:
            result = subprocess.run(
                command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout.strip(),
                'stderr': result.stderr.strip(),
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Git command timeout',
                'returncode': -1
            }
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': -1
            }
    
    def pull_latest(self):
        """Đồng bộ code deploy với origin/main, kể cả khi remote bị force-push."""
        log_to_file(f"{self.log_prefix} Đang pull code từ GitHub...")

        status = self._run_git_command(
            ['git', 'status', '--porcelain', '--untracked-files=all']
        )
        if not status['success']:
            return self._pull_error(status)
        blocking_changes = self._blocking_worktree_changes(status['stdout'])
        if blocking_changes:
            return {
                'success': False,
                'message': (
                    "❌ VPS đang có file chưa commit nên bot không tự ghi đè.\n"
                    f"```\n{blocking_changes[:1500]}\n```"
                ),
                'changed_files': [],
            }

        current = self._run_git_command(['git', 'rev-parse', 'HEAD'])
        if not current['success']:
            return self._pull_error(current)
        old_head = current['stdout']

        fetched = self._run_git_command(['git', 'fetch', 'origin', 'main'])
        if not fetched['success']:
            return self._pull_error(fetched)

        remote = self._run_git_command(['git', 'rev-parse', '--verify', 'origin/main'])
        if not remote['success']:
            return self._pull_error(remote)
        new_head = remote['stdout']

        if old_head == new_head:
            return {
                'success': True,
                'message': "✅ Code đã ở phiên bản mới nhất.",
                'changed_files': [],
            }

        backup_branch = None
        ancestor = self._run_git_command(
            ['git', 'merge-base', '--is-ancestor', old_head, new_head]
        )
        if not ancestor['success']:
            backup_branch = self._create_backup_branch(old_head)
            if not backup_branch:
                return {
                    'success': False,
                    'message': "❌ Không tạo được nhánh backup trước khi đồng bộ lịch sử.",
                    'changed_files': [],
                }

        changed_files = self._get_changed_files(old_head, new_head)
        reset = self._run_git_command(['git', 'reset', '--hard', 'origin/main'])
        if not reset['success']:
            return self._pull_error(reset)

        short_head = new_head[:7]
        details = [f"✅ Đã cập nhật VPS tới `{short_head}`."]
        if backup_branch:
            details.append(
                f"Remote đã viết lại lịch sử; commit cũ được giữ tại `{backup_branch}`."
            )
        log_to_file(f"{self.log_prefix} ✅ Pull thành công: {old_head[:7]} -> {short_head}")
        return {
            'success': True,
            'message': "\n".join(details),
            'changed_files': changed_files,
        }

    @classmethod
    def _blocking_worktree_changes(cls, porcelain_output):
        blocking = []
        for line in str(porcelain_output or '').splitlines():
            if not line:
                continue
            path = line[3:].strip().strip('"').replace("\\", "/")
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip().strip('"')
            if any(
                path == prefix.rstrip("/") or path.startswith(prefix)
                for prefix in cls.RUNTIME_PATH_PREFIXES
            ):
                continue
            if "/__pycache__/" in f"/{path}" or path.endswith((".pyc", ".pyo")):
                continue
            blocking.append(line)
        return "\n".join(blocking)

    def _pull_error(self, result):
        error_msg = result['stderr'] or result['stdout'] or 'Git command failed'
        log_to_file(f"{self.log_prefix} ❌ Pull thất bại: {error_msg}")
        return {
            'success': False,
            'message': f"❌ Pull thất bại!\n{error_msg}",
            'changed_files': [],
        }

    def _create_backup_branch(self, commit_hash):
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        base_name = f"backup/gitpull-{timestamp}-{commit_hash[:7]}"
        branch_name = base_name
        suffix = 2
        while self._run_git_command(
            ['git', 'show-ref', '--verify', '--quiet', f"refs/heads/{branch_name}"]
        )['success']:
            branch_name = f"{base_name}-{suffix}"
            suffix += 1

        result = self._run_git_command(['git', 'branch', branch_name, commit_hash])
        if not result['success']:
            error_msg = result['stderr'] or result['stdout'] or 'Không rõ lỗi'
            log_to_file(
                f"{self.log_prefix} ❌ Không tạo được branch backup: {error_msg}"
            )
            return None
        return branch_name
    
    def get_status(self):
        """Kiểm tra trạng thái git"""
        result = self._run_git_command(['git', 'status', '-s'])
        
        if result['success']:
            return {
                'success': True,
                'status': result['stdout'] or '✅ Không có thay đổi (clean)',
                'has_changes': bool(result['stdout'])
            }
        else:
            return {
                'success': False,
                'status': result['stderr'],
                'has_changes': False
            }
    
    def get_last_commit(self):
        """Lấy thông tin commit cuối cùng"""
        result = self._run_git_command(['git', 'log', '-1', '--oneline'])
        
        if result['success']:
            return {
                'success': True,
                'commit': result['stdout']
            }
        else:
            return {
                'success': False,
                'commit': None
            }
    
    def _get_changed_files(self, old_head='HEAD@{1}', new_head='HEAD'):
        """Lấy danh sách files đã thay đổi"""
        result = self._run_git_command(['git', 'diff', '--name-only', old_head, new_head])
        
        if result['success']:
            files = result['stdout'].split('\n') if result['stdout'] else []
            return [f for f in files if f.strip()]
        return []
    
    def get_branch(self):
        """Lấy tên branch hiện tại"""
        result = self._run_git_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        
        if result['success']:
            return result['stdout']
        return None
    
    def get_remote_url(self):
        """Lấy URL của remote repository"""
        result = self._run_git_command(['git', 'config', '--get', 'remote.origin.url'])
        
        if result['success']:
            return result['stdout']
        return None
