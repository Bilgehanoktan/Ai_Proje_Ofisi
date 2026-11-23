/* Linux-only native source. No runtime activation or installation by this file.
 * Caller must already inhabit the exact independently enrolled rootless user,
 * mount, network and PID namespaces. clone3 atomically places the child in the
 * enrolled cgroup; no post-spawn cgroup-attach window is accepted.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/sched.h>
#include <linux/magic.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/audit.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/statfs.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>
#include <signal.h>

#if defined(__x86_64__)
#define R58_ARCH AUDIT_ARCH_X86_64
#elif defined(__aarch64__)
#define R58_ARCH AUDIT_ARCH_AARCH64
#else
#error unsupported_r58_seccomp_architecture
#endif
#define DENY_NR(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,(n),0,1), BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM)
static int r58_filter(void) {
    struct sock_filter filter[]={
      BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,arch)),
      BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,R58_ARCH,1,0),
      BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
      BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,nr)),
      /* Reject alternate ABI syscall numbers as well. */
      BPF_JUMP(BPF_JMP|BPF_JGE|BPF_K,0x40000000U,0,1),
      BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
      DENY_NR(SYS_clone),DENY_NR(SYS_clone3),
#ifdef SYS_fork
      DENY_NR(SYS_fork),
#endif
#ifdef SYS_vfork
      DENY_NR(SYS_vfork),
#endif
      DENY_NR(SYS_socket),DENY_NR(SYS_socketpair),DENY_NR(SYS_connect),
      DENY_NR(SYS_bind),DENY_NR(SYS_listen),DENY_NR(SYS_accept),DENY_NR(SYS_accept4),
      DENY_NR(SYS_mount),DENY_NR(SYS_umount2),DENY_NR(SYS_setns),DENY_NR(SYS_unshare),
      DENY_NR(SYS_ptrace),DENY_NR(SYS_bpf),DENY_NR(SYS_kill),
      BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program={sizeof(filter)/sizeof(filter[0]),filter};
    return prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&program);
}

int r65_spawn(int cgroup_fd,int executable_fd,int workspace_fd,char *const argv[],
              int engine_stdin,int engine_stdout,int engine_stderr,pid_t *out_pid,int *out_pidfd) {
    struct statfs fs;
    struct stat pipe_stats[3];
    int pipes[3]={engine_stdin,engine_stdout,engine_stderr};
    int modes[3]={O_RDONLY,O_WRONLY,O_WRONLY};
    struct clone_args args={0};
    int pidfd=-1;
    pid_t parent=getpid();
    long child;
    if(!out_pid || !out_pidfd || !argv || !argv[0] || geteuid()==0) {
        errno=EPERM;return -1;
    }
    if(fstatfs(cgroup_fd,&fs)<0 || fs.f_type!=CGROUP2_SUPER_MAGIC) {
        errno=EINVAL;return -1;
    }
    /* Validate only private FIFO handles. No socket/DB/key FD can be stdio. */
    for(int i=0;i<3;i++) {
        int flags=fcntl(pipes[i],F_GETFL);
        if(pipes[i]<0 || fstat(pipes[i],&pipe_stats[i])<0 || !S_ISFIFO(pipe_stats[i].st_mode)
           || flags<0 || (flags&O_ACCMODE)!=modes[i] || (flags&O_NONBLOCK)) {
            errno=EINVAL;return -1;
        }
        for(int j=0;j<i;j++)if(pipe_stats[i].st_dev==pipe_stats[j].st_dev && pipe_stats[i].st_ino==pipe_stats[j].st_ino) {
            errno=EINVAL;return -1;
        }
    }
    args.flags=CLONE_INTO_CGROUP|CLONE_PIDFD;
    args.cgroup=(uint64_t)cgroup_fd;
    args.pidfd=(uintptr_t)&pidfd;
    args.exit_signal=SIGCHLD;
    child=syscall(SYS_clone3,&args,sizeof(args));
    if(child<0)return -1; /* ENOSYS/EPERM never falls back to fork+attach. */
    if(child==0) {
        int exec_copy,dir_copy,stdio_copy[3];
        char *const empty_env[]={NULL};
        /* Save descriptors before closing all inherited DB/socket/key handles. */
        exec_copy=fcntl(executable_fd,F_DUPFD_CLOEXEC,10);
        dir_copy=fcntl(workspace_fd,F_DUPFD_CLOEXEC,10);
        if(exec_copy<0 || dir_copy<0 || fchdir(dir_copy)<0) _exit(125);
        for(int i=0;i<3;i++) {
            stdio_copy[i]=fcntl(pipes[i],F_DUPFD_CLOEXEC,10);
            if(stdio_copy[i]<0)_exit(125);
        }
        for(int i=0;i<3;i++)if(dup3(stdio_copy[i],i,0)<0)_exit(125);
        if(dup3(exec_copy,3,O_CLOEXEC)<0) _exit(125);
        if(syscall(SYS_close_range,4U,~0U,0)<0) _exit(125);
        if(setsid()<0 || prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=parent
           || prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)<0 || r58_filter()<0) _exit(125);
        /* Sealed ELF memfd has no mutable pathname or script interpreter. */
        syscall(SYS_execveat,3,"",argv,empty_env,AT_EMPTY_PATH);
        _exit(126);
    }
    *out_pid=(pid_t)child;*out_pidfd=pidfd;
    return 0; /* This is process creation, NOT exec completion or DB acceptance. */
}
