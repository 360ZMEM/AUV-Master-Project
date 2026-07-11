/* prjConfig.c - dynamicaly generated configuration file */


/*
GENERATED: Wed Aug 17 13:57:54 +0800 2022
DO NOT EDIT - file is regenerated whenever the project changes.
This file contains the non-BSP system initialization code
for Create a bootable VxWorks image (custom configured).
*/


/* includes */

#include <vxWorks.h>
#include <config.h>
#include <../src/hwif/h/console/pcConsole.h>
#include <../src/hwif/h/console/vxbI8042Kbd.h>
#include <../src/hwif/h/console/vxbM6845Vga.h>
#include <../src/hwif/h/end/fei8255xVxbEnd.h>
#include <../src/hwif/h/mii/genericPhy.h>
#include <../src/hwif/h/mii/miiBus.h>
#include <adrSpaceLib.h>
#include <applUtilLib.h>
#include <auxv.h>
#include <cacheLib.h>
#include <classLib.h>
#include <configNet.h>
#include <coprocLib.h>
#include <cplusLib.h>
#include <cpuPwrLib.h>
#include <cpuPwrMgr.h>
#include <dbgLib.h>
#include <dosFsLib.h>
#include <drv/dma/iPIIX4Dma.h>
#include <drv/erf/erfLib.h>
#include <drv/hdisk/ataDrv.h>
#include <drv/manager/device.h>
#include <drv/wdb/wdbEndPktDrv.h>
#include <drv/wdb/wdbVioDrv.h>
#include <edrLib.h>
#include <end.h>
#include <endLib.h>
#include <envLib.h>
#include <eventLib.h>
#include <excLib.h>
#include <fioLib.h>
#include <fsEventUtilLib.h>
#include <fsMonitor.h>
#include <ftpLib.h>
#include <hashLib.h>
#include <hookLib.h>
#include <hostLib.h>
#include <hwif/vxbus/vxBus.h>
#include <hwif/vxbus/vxbPciLib.h>
#include <hwif/vxbus/vxbPlbLib.h>
#include <intLib.h>
#include <ioLib.h>
#include <iosLib.h>
#include <iosScLib.h>
#include <isrDeferLib.h>
#include <jobQueueLib.h>
#include <ledLib.h>
#include <loadElfLib.h>
#include <logLib.h>
#include <loginLib.h>
#include <lstLib.h>
#include <m2IfLib.h>
#include <math.h>
#include <memLib.h>
#include <moduleLib.h>
#include <msgQLib.h>
#include <muxLib.h>
#include <muxTkLib.h>
#include <net/mbuf.h>
#include <net/utils/ifconfig.h>
#include <netBufLib.h>
#include <netDrv.h>
#include <netLib.h>
#include <netdb.h>
#include <objLib.h>
#include <pingLib.h>
#include <pipeDrv.h>
#include <pmLib.h>
#include <private/adrSpaceLibP.h>
#include <private/cpuPwrLibP.h>
#include <private/eventPointStubLibP.h>
#include <private/excLibP.h>
#include <private/ftpLibP.h>
#include <private/funcBindP.h>
#include <private/intLibP.h>
#include <private/isrLibP.h>
#include <private/jobLibP.h>
#include <private/kernelBaseLibP.h>
#include <private/kernelLibP.h>
#include <private/nbioLogLibP.h>
#include <private/offsetsP.h>
#include <private/pgMgrLibP.h>
#include <private/pgPoolLibP.h>
#include <private/pgPoolPhysLibP.h>
#include <private/pgPoolVirtLibP.h>
#include <private/poolLibP.h>
#include <private/rtpDbgCmdLibP.h>
#include <private/rtpLibP.h>
#include <private/sdLibP.h>
#include <private/shellHistLibP.h>
#include <private/shellLibP.h>
#include <private/syscallLibP.h>
#include <private/taskLibP.h>
#include <private/tipLibP.h>
#include <private/vmLibP.h>
#include <private/vxMemProbeLibP.h>
#include <private/vxdbgCpuLibP.h>
#include <private/vxdbgRtpLibP.h>
#include <private/workQLibP.h>
#include <ptyDrv.h>
#include <qPriBMapLib.h>
#include <rawFsLib.h>
#include <rebootLib.h>
#include <remLib.h>
#include <rtpLib.h>
#include <sdLib.h>
#include <selectLib.h>
#include <semLib.h>
#include <shellInterpLib.h>
#include <shellLib.h>
#include <shlLib.h>
#include <sigLib.h>
#include <sioLib.h>
#include <stdio.h>
#include <string.h>
#include <symLib.h>
#include <sysLib.h>
#include <sysSymTbl.h>
#include <syscallLib.h>
#include <syscallTbl.h>
#include <sysctlLib.h>
#include <taskHookLib.h>
#include <taskLib.h>
#include <taskUtilLib.h>
#include <taskVarLib.h>
#include <telnetLib.h>
#include <tickLib.h>
#include <timexLib.h>
#include <ttyLib.h>
#include <tyLib.h>
#include <unistd.h>
#include <unldLib.h>
#include <usrConfig.h>
#include <usrLib.h>
#include <version.h>
#include <vmLib.h>
#include <vxAtomicLib.h>
#include <vxBusLib.h>
#include <vxLib.h>
#include <vxbTimerLib.h>
#include <wait.h>
#include <wdLib.h>
#include <wdb/wdb.h>
#include <wdb/wdbBpLib.h>
#include <wdb/wdbCommIfLib.h>
#include <wdb/wdbLib.h>
#include <wdb/wdbLibP.h>
#include <wdb/wdbMbufLib.h>
#include <wdb/wdbRpcLib.h>
#include <wdb/wdbRtIfLib.h>
#include <wdb/wdbRtpLibP.h>
#include <wdb/wdbSvcLib.h>
#include <wdb/wdbUdpLib.h>
#include <wdb/wdbVioLib.h>
#include <xbdBlkDev.h>


/* imports */

IMPORT char etext [];                   /* defined by loader */
IMPORT char end [];                     /* defined by loader */
IMPORT char edata [];                   /* defined by loader */

/* forward declarations */

IMPORT void i8042vxbRegister (void);
IMPORT void vxbFileNvRamRegister(void);
IMPORT void ns16550SioRegister (void);
IMPORT void vxbI8253TimerDrvRegister (void);
IMPORT void m6845vxbRegister (void);
IMPORT STATUS adrSpaceShellCmdInit (void);
IMPORT u_short checksum (u_short *, int);
IMPORT STATUS dbgShellCmdInit ();
IMPORT STATUS usrFsShellCmdInit ();
IMPORT STATUS edrShellCmdInit ();
IMPORT void endEtherHdrInit (void);
IMPORT STATUS eventPointStubLibInit (void);
extern STATUS mmanShowInit ();
IMPORT STATUS mmanShowShellCmdInit (void);
IMPORT STATUS memEdrRtpShellCmdInit (void);
IMPORT STATUS memEdrRtpShowInit (void);
IMPORT STATUS memEdrShellCmdInit (void);
IMPORT void memRtpLibInit (UINT heapSize,UINT heapOptions);
extern STATUS moduleShellCmdInit (void);
IMPORT STATUS hostnameSetup (char * );
IMPORT STATUS objInfoInit (void);
IMPORT void pentiumPciRegister (void);
extern void clockLibInit (void);
extern STATUS mmanFdLibInit (void);
extern STATUS usrRtpLibInit();
IMPORT STATUS rtpShowShellCmdInit (void);
IMPORT void windScInit (void);
IMPORT void mmanScLibInit (void);
extern void usrPosixScInit (void);
IMPORT void sdScInit (void);
IMPORT void shlScLibInit (void);
IMPORT STATUS sockScLibInit (void);
IMPORT STATUS sysctlScLibInit (void);
IMPORT void semBCreateLibInit (void);
IMPORT void semCCreateLibInit (void);
IMPORT void semMCreateLibInit (void);
IMPORT STATUS sdShowShellCmdInit (void);
IMPORT STATUS symShellCmdInit ();
IMPORT void taskCreateLibInit (void);
IMPORT STATUS taskShellCmdInit ();
IMPORT STATUS vxbDelayLibInit (void);
extern STATUS unloadShellCmdInit (void);
IMPORT STATUS vmShowShellCmdInit (void);
IMPORT STATUS vxbSysClkLibInit (void);
IMPORT void vxmux_mux_mblk_init (void);
IMPORT void usrWdbInitDone (void);
IMPORT void usrWdbInit (void);


/* BSP_STUBS */



/* configlettes */

#include <sysComms.c>
#include <edrStub.c>
#include <hwif/hwMemAlloc.uc>
#include <hwif/vxbPci.bc>
#include <hwif/vxbVerChk.uc>
#include <intrinsics.c>
#include <ipnet/ipcom_config.c>
#include <ipnet/ipcom_ipd_config.c>
#include <ipnet/ipcom_telnets_config.c>
#include <ipnet/ipftps_config.c>
#include <ipnet/ipftps_example.c>
#include <ipnet/ipnet_config.c>
#include <ipnet/iptcp_config.c>
#include <net/coreip/apps/usrFtp.c>
#include <net/coreip/apps/usrNetHostTblCfg.c>
#include <net/coreip/usrBootLine.c>
#include <net/coreip/usrNetApplUtil.c>
#include <net/coreip/usrNetBoot.c>
#include <net/coreip/usrNetDaemon.c>
#include <net/coreip/usrNetEndLib.c>
#include <net/coreip/usrNetIfconfig.c>
#include <net/coreip/usrNetRemoteCfg.c>
#include <net/coreip/usrNetSysctl.c>
#include <sysAta.c>
#include <sysClkInit.c>
#include <usrAta.c>
#include <usrBreakpoint.c>
#include <usrCache.c>
#include <usrCoprocs.c>
#include <usrDosfs.c>
#include <usrEdrInit.c>
#include <usrHwSysctl.c>
#include <usrIsrDefer.c>
#include <usrKernel.c>
#include <usrKernelStack.c>
#include <usrMemEdr.c>
#include <usrMmuInit.c>
#include <usrPcConsole.c>
#include <usrPmInit.c>
#include <usrPosixSc.c>
#include <usrSecurity.c>
#include <usrSemLib.c>
#include <usrSerial.c>
#include <usrShell.c>
#include <usrStandalone.c>
#include <usrStartup.c>
#include <usrSysHwInit2.c>
#include <usrSysSymTbl.c>
#include <usrSysctl.c>
#include <usrTip.c>
#include <usrVxbSioChanUtil.c>
#include <usrVxbTimerSys.c>
#include <usrWdbBanner.c>
#include <usrWdbBp.c>
#include <usrWdbCore.c>
#include <usrWdbGopher.c>
#include <usrWdbSys.c>
#include <wdbEnd.c>


/******************************************************************************
*
* usrInit - pre-kernel initialization
*/

void usrInit (int startType)
    {
    sysStart (startType);               /* clear BSS and set up the vector table base address. */
    cacheLibInit (USER_I_CACHE_MODE, USER_D_CACHE_MODE); /* include cache support */
    excVecInit ();                      /* exception handling */
    sysHwInit ();                       /* call the BSPs sysHwInit routine during system startup */
    usrCacheEnable ();                  /* optionally enable caches */
    objOwnershipInit ();                /* object management ownership */
    objInfoInit ();                     /* object management routines that requires lookup in a list of objects, such as the objNameToId() routine. */
    objLibInit ((FUNCPTR)FUNCPTR_OBJ_MEMALLOC_RTN, FUNCPTR_OBJ_MEMFREE_RTN, OBJ_MEM_POOL_ID, OBJ_LIBRARY_OPTIONS); /* object management */
    vxMemProbeInit ();                  /* Initialize vxMemProbe exception handler support */
    classListLibInit ();                /* object class list management */
    semLibInit ();                      /* semaphore support infrastructure */
                                        /* mutex semaphores */
                                        /* mutex semaphore creation routine */
    classLibInit ();                    /* object class management */
    kernelBaseInit ();                  /* required component DO NOT REMOVE. */
    usrKernelInit (VX_GLOBAL_NO_STACK_FILL); /* context switch and interrupt handling (DO NOT REMOVE). */
    }



/******************************************************************************
*
* usrLoaderInit - The target loader initialization sequence
*/

void usrLoaderInit (void)
    {
    moduleLibInit ();                   /* Support library for module entities */
    loadElfInit();                      /* ELF loader */
    loadLibInit (STORE_ABS_SYMBOLS);    /* Allows modules to be downloaded into running targets */
    unldLibInit ();                     /* Permits removal of dynamically downloaded modules */
    }



/******************************************************************************
*
* usrShowInit - enable object show routines
*/

void usrShowInit (void)
    {
    taskShowInit ();                    /* task show routine */
    memShowInit ();                     /* memory show routine */
    taskHookShowInit ();                /* task hook show routine */
    symShowInit ();                     /* Routines to display information about symbols and symbol tables */
    vmShowInit ();                      /* VM library show routine */
    edrShowInit ();                     /* ED&R show routines */
                                        /* handle show routines */
    adrSpaceShowInit();                 /* Address Space Allocator Show Routines: display information on the system address space allocator. */
    pgMgrShowInit();                    /* Page manager show routines: display information on page managers. */
    pgPoolShowInit();                   /* Generic page pool allocator show routines: display information on page pools. */
    rtpShowInit ();                     /* Display information on RTP. */
    sdShowInit ();                      /* Display information on Shared Data. */
    shlShowInit ();                     /* Display information on Shared Libraries */
    mmanShowInit();                     /* Show routines for memory mapped objects */
    coprocShowInit ();                  /* task coprocessor registers */
    }



/******************************************************************************
*
* usrSymTblInit - Enable onboard symbol tables
*/

void usrSymTblInit (void)
    {
    usrSysSymTblInit ();                /* initialize system symbol table */
    usrStandaloneInit ();               /* Preferred method if not booting from the network */
    }



/******************************************************************************
*
* usrShellCmdInit - The kernel shell commands initialization sequence
*/

void usrShellCmdInit (void)
    {
    taskShellCmdInit ();                /* List of commands for the shell command interpreter related to tasks. */
    dbgShellCmdInit ();                 /* List of commands for the shell command interpreter related to debugging. */
    symShellCmdInit ();                 /* List of commands for the shell command interpreter related to symbol access. */
    usrFsShellCmdInit ();               /* List of commands for the shell command interpreter related to file system. */
    edrShellCmdInit ();                 /* List of commands for the shell command interpreter related to ED&R. */
    vmShowShellCmdInit ();              /* Virtual Memory show commands for the shell command interpreter. */
    adrSpaceShellCmdInit ();            /* Address space commands for the shell command interpreter. */
    sdShowShellCmdInit ();              /* Shared data show commands for the shell command interpreter. */
    mmanShowShellCmdInit ();            /* mapped files commands for the shell command interpreter. */
    memEdrShellCmdInit ();              /* Memory Ed&R commands for the shell command interpreter. */
    memEdrRtpShellCmdInit ();           /* Memory ED&R shell commands related to processes for the shell command interpreter. */
    moduleShellCmdInit();               /* Target loader commands for the shell command interpreter. */
    unloadShellCmdInit();               /* Unloader commands for the shell command interpreter. */
    rtpShellCmdInit ();                 /* List of commands for the shell command interpreter related to processes. */
    rtpShowShellCmdInit ();             /* List of process show commands for the shell command interpreter. */
    shlShellCmdInit ();                 /* List of SHL commands for the shell command interpreter */
    histShellCmdInit ();                /* Saving and loading commands for the shell command interpreter history. */
    }



/******************************************************************************
*
* usrShellInit - The kernel shell initialization sequence
*/

void usrShellInit (void)
    {
    shellLibInit ();                    /* Handles the shell core files */
    shellHistLibInit ();                /* Allows to save and load the shell history */
    dbgInit ();                         /* Breakpoints and stack tracer on target. Not needed for remote debugging with Workbench. */
    vxdbgRtpLibInit ();                 /* Initialize process debugging library. */
    ledModeRegister (viLedLibInit);     /* Editing mode similar to the Vi editing mode */
    shellInterpRegister (shellInterpCInit); /* The C interpreter for the kernel shell */
    shellInterpRegister (shellInterpCmdInit); /* The command interpreter for the kernel shell */
    usrShellCmdInit ();                 /* The kernel shell commands initialization sequence */
    usrShell ();                        /* Interpreter for interactive development, prototyping, debugging and testing. */
    }



/******************************************************************************
*
* usrToolsInit - software development tools
*/

void usrToolsInit (void)
    {
    timexInit ();                       /* utility to measure function execution time */
    eventPointStubLibInit ();           /* stub eventpoint implementation */
    usrLoaderInit ();                   /* The target loader initialization sequence */
    usrSymTblInit ();                   /* Enable onboard symbol tables */
    usrWdbInit ();                      /* WDB agent is initialized when kernel has been initialized. It then can debug whole system and supports task and system mode. */
    rtpDbgCmdLibInit ();                /* Allows to send commands to perform operations in an RTP context */
    usrTipInit (TIP_CONFIG_STRING, TIP_ESCAPE_CHARACTER); /* interactive utility to connect to and manage multiple serial lines */
    usrShowInit ();                     /* enable object show routines */
    usrRtpLibInit ();                   /* List of commands for the shell C interpreter related to RTPs. */
    usrShellInit ();                    /* The kernel shell initialization sequence */
    }



/******************************************************************************
*
* usrKernelCoreInit - core kernel facilities
*/

void usrKernelCoreInit (void)
    {
    eventLibInit (VXEVENTS_OPTIONS);    /* VxWorks events */
    semDeleteLibInit ();                /* semaphore deletion routines */
                                        /* binary semaphores */
                                        /* counting semaphores */
                                        /* reader/writer semaphores */
    semOpenInit ();                     /* open/close/unlink semaphore modules */
    msgQLibInit ();                     /* message queues */
    msgQOpenInit ();                    /* open/close/unlink message queue modules */
    wdLibInit ();                       /* watchdog timers */
    taskOpenInit ();                    /* open/close/unlink task modules */
    taskCreateHookInit ();              /* user callouts on task creation/deletion */
                                        /* binary semaphore creation routine */
                                        /* counting semaphore creation routine */
                                        /* reader/writer semaphore creation routine */
    taskCreateLibInit ();               /* Capability to dynamically instantiate and delete tasks */
    msgQCreateLibInit ();               /* message queue creation and deletion library */
    wdCreateLibInit ();                 /* watchdog timers creation and deletion library */
    wdbTaskHookInit ();                 /* task hooks debug support */
    }



/******************************************************************************
*
* usrKernelExtraInit - extended kernel facilities
*/

void usrKernelExtraInit (void)
    {
    hashLibInit ();                     /* hash library */
    symLibInit ();                      /* Set of routines to manipulate symbols and symbol tables */
    taskVarInit ();                     /* allow global variables to be made private to a task */
    sigInit (POSIX_SIGNAL_MODE);        /* signals */
    clockLibInit ();                    /* POSIX clocks */
    syscallHookLibInit ();              /* Add hook routines to be called on system calls. */
    }



/******************************************************************************
*
* usrIosCoreInit - core I/O system
*/

void usrIosCoreInit (void)
    {
    selectInit (NUM_FILES);             /* select */
    iosInit (NUM_DRIVERS, NUM_FILES, "/null"); /* Basic IO system component */
    iosPathLibInit ();                  /* File System IO component */
    iosRmvLibInit ();                   /* Removable IO component */
    iosPxLibInit (IOS_POSIX_PSE52_MODE); /* POSIX IO component */
    iosRtpLibInit ();                   /* RTP IO component */
                                        /* Miscellaneous IO component */
    usrIsrDeferInit ();                 /* ISR deferral facility */
    tyLibInit (TYLIB_XOFF_PCNT, TYLIB_XON_PCNT, TYLIB_WRT_THRESHLD); /* Allows communication between processes */
    ttyDrv ();                          /* terminal driver */
    usrSerialInit ();                   /* SIO component */
    usrPcConsoleInit ();                /* PC console component */
    coprocLibInit();                    /* generalized coprocessor support */
    }



/******************************************************************************
*
* usrIosExtraInit - extended I/O system
*/

void usrIosExtraInit (void)
    {
    excShowInit ();                     /* exception show routines */
    jobLibInit (JOB_TASK_STACK_SIZE);   /* miscellaneous support task */
    excInit (MAX_ISR_JOBS);             /* interrupt-level job facility */
    logInit (consoleFd, MAX_LOG_MSGS);  /* message logging */
    nbioLogInit (consoleFd, INIT_NBIO_MSGS); /* non-blocking message logging */
    pipeDrv ();                         /* pipes */
    stdioInit ();                       /* buffered IO library */
    fioLibInit ();                      /* formatting for printf, scanf, etc. */
    floatInit ();                       /* allow printf and others to format floats correctly */
    erfLibInit (ERF_MAX_USR_CATEGORIES, ERF_MAX_USR_TYPES); /* Event Reporting Framework */
    devInit (DEVICE_MANAGER_MAX_NUM_DEVICES); /* Device Manager */
    xbdInit ();                         /* Extended Block Device */
    xbdBlkDevLibInit (XBD_BLK_DEV_TASK_PRIORITY, XBD_BLK_DEV_DIRECT_BIO_HANDLING); /* XBD Block Device Wrapper */
    fsMonitorInit ();                   /* File System Monitor */
    fsEventUtilLibInit ();              /* File System Event Utilities */
    usrDosfsInit (DOSFS_DEFAULT_MAX_FILES, DOSFS_DEFAULT_CREATE_OPTIONS); /* MS-DOS-Compatible File System: dosFs main module */
    dosFsShowInit();                    /* Show routines for Dos FS */
    rawFsInit (NUM_RAWFS_FILES);        /* Raw block device file system interface */
    ptyDrv ();                          /* Allows communication between processes */
    sysAtaSetup ();                     /* support DMA on ATA/ATAPI disks */
    usrAtaInit (); usrAtaConfig (0, 0, FS_NAMES_ATA_PRIMARY_MASTER, ATA_DIRECT_BIO_HANDLING); usrAtaConfig (0, 1, FS_NAMES_ATA_PRIMARY_SLAVE, ATA_DIRECT_BIO_HANDLING); usrAtaConfig (1, 0, FS_NAMES_ATA_SECONDARY_MASTER, ATA_DIRECT_BIO_HANDLING); usrAtaConfig (1, 1, FS_NAMES_ATA_SECONDARY_SLAVE, ATA_DIRECT_BIO_HANDLING); /* ATA hard drive component */
    usrBootLineParse (BOOT_LINE_ADRS);  /* parse some boot device configuration info */
    }



/******************************************************************************
*
* usrNetAppInit - 
*/

void usrNetAppInit (void)
    {
    telnetcInit ();                     /* telnet client by use of telnet protocol */
    usrSecurity ();                     /* rlogin and telnet password protection */
    usrFtpInit();                       /* File Transfer Protocol (FTP) library */
    }



/******************************************************************************
*
* usrNetHostInit - 
*/

void usrNetHostInit (void)
    {
    usrNetHostTblSetup ();              /* host table support */
    hostnameSetup (pTgtName);           /* assign local hostname to target */
    }



/******************************************************************************
*
* usrNetRemoteInit - 
*/

void usrNetRemoteInit (void)
    {
    remLibInit(RSH_STDERR_SETUP_TIMEOUT); /* Remote Command Library */
    remLibSysctlInit();                 /* Network sysctl tree support for remlib */
                                        /* Allows access to file system on boot host */
    usrNetRemoteCreate ();              /* Allows access to file system on boot host */
    }



/******************************************************************************
*
* usrNetUtilsInit - Initialize network utility routines
*/

void usrNetUtilsInit (void)
    {
    usrNetIfconfigInit ();              /* ifconfig */
    }



/******************************************************************************
*
* usrNetworkInit - Initialize the network subsystem
*/

void usrNetworkInit (void)
    {
    usrNetApplUtilInit ();              /* Stack and Application Logging Utility */
    usrNetBoot ();                      /* Copy boot parameters for futher use by network */
    netBufLibInitialize (NETBUF_LEADING_CLSPACE_DRV); /* Network Buffer Library */
    netBufPoolInit ();                  /* netBufLib Generic Pool */
    linkBufPoolInit ();                 /* Network Buffer Library */
    vxmux_null_buf_init ();             /* Minimal clusterless network pool implementation for IPCOM */
    jobQueueLibInit();                  /* jobQueueLib prioritized work deferral mechanism */
    usrNetDaemonInit(NET_JOB_NUM_CFG, NET_TASK_PRIORITY, NET_TASK_OPTIONS, NET_TASK_STACKSIZE); /* Network Daemon Support */
    usrNetmaskGet ();                   /* Extracts netmask value from address field */
    usrNetSysctlInit();                 /* Networking System control support */
    usrNetHostInit ();                  /* initialize host table */
    rtpHostLibInit ();                  /* network sysctl tree support for host tables */
    rtpGetaddrinfoInit ();              /* network sysctl tree support for RTP getaddrinfo() */
    muxCommonInit();                    /* MUX common support (all protocol and device styles) */
    muxLibInit();                       /* Support muxBind() protocols and their APIs */
    mux2LibInit();                      /* Support mux2Bind() protocols and their APIs */
    muxTkLibInit();                     /* Support muxTkBind() protocols and their APIs */
    vxmux_mux_mblk_init ();             /* MUX private support for M_BLK/Ipcom_pkt conversion */
    mux2OverEndInit();                  /* Support mux2Bind() protocols over END-style devices */
    muxTkOverEndInit();                 /* Support muxTkBind() protocols over END-style devices */
    endEtherHdrInit ();                 /* M_BLK ethernet/802.3 header build and parse */
    endLibInit();                       /* Support for END-style network devices. */
    usrNetRemoteInit ();                /* initialize network remote I/O access */
    usrNetEndLibInit();                 /* Support for network devices using MUX/END interface. */
    ipcom_create ();                    /* VxWorks IPCOM */
    netSysctlInit (TRUE);               /* Integrates IPNet sysctl nodes into VxWorks sysctl tree. */
    usrNetUtilsInit ();                 /* Initialize network utility routines */
    usrNetAppInit ();                   /* initialize network application protocols */
    }



/******************************************************************************
*
* usrScInit - The system call initialization sequence
*/

void usrScInit (void)
    {
    usrPosixScInit ();                  /* system call handlers for POSIX based calls */
    sockScLibInit ();                   /* System call support for socket API */
    memRtpLibInit (RTP_HEAP_INIT_SIZE,RTP_HEAP_DEFAULT_OPTIONS); /* Initializes memory parameters to pass to RTP */
    windScInit ();                      /* system call handlers for WIND kernel */
    mmanScLibInit ();                   /* system call handlers for memory management */
    sdScInit ();                        /* system call handlers for shared data */
    shlScLibInit ();                    /* system call handlers for shared libraries */
    iosScLibInit ();                    /* IOS system calls */
    sysctlScLibInit ();                 /* System call support for sysctl() */
    }



/******************************************************************************
*
* usrRoot - entry point for post-kernel initialization
*/

void usrRoot (char *pMemPoolStart, unsigned memPoolSize)
    {
    usrKernelCoreInit ();               /* core kernel facilities */
    cpuPwrFrameWorkInit ( CPU_PWR_TASK_P_STATE, CPU_PWR_ISR_P_STATE, CPU_PWR_UTIL_PERIOD1, CPU_PWR_UTIL_PERIOD2, CPU_PWR_HIGH_THRESHOLD, CPU_PWR_LOW_THRESHOLD ); /* CPU Power management framework Component */
    cpuPwrLightMgrInit();               /* CPU Power Light utilization manager Component */
    poolLibInit();                      /* memory pools of fixed size items */
    memEdrInit ();                      /* Memory Error Detection and Reporting */
    memInit (pMemPoolStart, memPoolSize, MEM_PART_DEFAULT_OPTIONS); /* full featured memory allocator */
    memEdrInit2();                      /* Memory Error Detection and Reporting */
    memEdrShowInit();                   /* Memory ED&R Show Routines */
    memEdrRtpShowInit();                /* Memory ED&R Show Routines for RTPs */
    memPartLibInit (pMemPoolStart, memPoolSize); /* core memory partition manager */
    memInfoInit ();                     /* memory allocator info routines */
    rtpHookLibInit (RTP_HOOK_TBL_SIZE); /* Add hook routines to be called on RTP operations. */
    usrSysctlInit();                    /* System control function */
    usrHwSysctlInit();                  /* System control hardware info registration */
    rtpLibInit (RTP_HOOK_TBL_SIZE, SYSCALL_HOOK_TBL_SIZE, RTP_SIGNAL_QUEUE_SIZE, TASK_USER_EXC_STACK_OVERFLOW_SIZE, TASK_USER_EXEC_STACK_OVERFLOW_SIZE, TASK_USER_EXEC_STACK_UNDERFLOW_SIZE, RTP_FD_NUM_MAX); /* Real Time Process. */
    sdLibInit (SD_HOOK_TBL_SIZE);       /* provide data sharing between RTPs or kernel */
    shlLibInit ();                      /* provide sharing of code between RTPs */
    pgPoolLibInit();                    /* Generic Page Pool Allocator */
    pgPoolVirtLibInit();                /* Page Pool Allocator for Virtual Space */
    pgPoolPhysLibInit();                /* Page Pool Allocator for Physical Space */
                                        /* basic MMU component */
    usrMmuInit ((VIRT_ADDR) pMemPoolStart, memPoolSize); /* MMU global map support */
    envLibInit (ENV_VAR_USE_HOOKS);     /* unix compatable environment variables */
    usrPmInit ();                       /* reboot-safe protected memory region manager */
    usrEdrInit ();                      /* reboot-safe protected error log */
    edrSystemDebugModeInit ();          /* a flag indicating the system is in 'debug' mode */
    usrSysHwInit2();                    /* call the usrSysHwInit2 routine during system startup */
    pgMgrLibInit();                     /* Page Manager Library */
    sysClkInit ();                      /* System clock component */
    edrStubInit ();                     /* protected error log stub initialization */
                                        /* Modified definitions for generalized coprocessor */
    usrIosCoreInit ();                  /* core I/O system */
    usrKernelExtraInit ();              /* extended kernel facilities */
    usrIosExtraInit ();                 /* extended I/O system */
    sockLibInit ();                     /* Socket API */
    usrNetworkInit ();                  /* Initialize the network subsystem */
    selTaskDeleteHookAdd ();            /* selectInit, part 2, install task delete hook */
    cplusCtorsLink ();                  /* run compiler generated initialization functions at system startup */
    cplusDemanglerInit ();              /* Support library for kernel shell and loader: provides human readable forms of C++ identifiers */
    usrScInit ();                       /* The system call initialization sequence */
    mmanFdLibInit();                    /* POSIX Memory Mapped Files for RTPs */
    usrToolsInit ();                    /* software development tools */
    usrAppInit ();                      /* call usrAppInit() (in your usrAppInit.c project file) after startup. */
    }



/******************************************************************************
*
* usrWdbInit - the WDB target agent
*/

void usrWdbInit (void)
    {
    wdbConfig ();                       /* software agent to support the Workbench tools */
    wdbMemLibInit ();                   /* read/write target memory */
    wdbSysModeInit ();                  /* A breakpoint stops the entire operating system. */
    wdbTaskModeInit (WDB_SPAWN_STACK_SIZE, WDB_TASK_PRIORITY, WDB_TASK_OPTIONS, WDB_STACK_SIZE, WDB_MAX_RESTARTS, WDB_RESTART_TIME); /* A breakpoint stops one task, while others keep running. */
    wdbEventLibInit ();                 /* asynchronous event handling needed for breakpoints etc. */
    wdbEvtptLibInit ();                 /* support library for breakpoints and other asynchronous events. */
    wdbRtpLibInit (WDB_RTP_PRIORITY);   /* RTP operations: creation, deletion, ... */
    wdbDirectCallLibInit ();            /* call arbitrary functions directly from WDB */
    wdbCtxLibInit ();                   /* create/delete/manipulate tasks */
    wdbRegsLibInit ();                  /* get/set registers */
    wdbExternRegLibInit ();             /* Register support for system mode WDB */
    wdbTaskRegLibInit ();               /* Coprocessor support for task in WDB */
    usrWdbGopherInit ();                /* information gathering language used by many tools */
    wdbCtxExitLibInit ();               /* ability to notify the host when a task exits */
    wdbExcLibInit ();                   /* notify the host when an exception occurs */
    wdbFuncCallLibInit ();              /* asynchronous function calls */
    wdbVioLibInit ();                   /* low-level virtual I/O handling */
    wdbVioDrv ("/vio");                 /* vxWorks driver for accessing virtual I/O */
    usrWdbBp ();                        /* core breakpoint library */
    wdbBpSyncLibInit ();                /* Breakpoint synchronization component */
    wdbTaskBpLibInit ();                /* task-mode breakpoint library */
    wdbRtpBpLibInit ();                 /* task-mode RTP breakpoint library */
    wdbRtpCtrlLibInit ();               /* Allow to stop real time processes when they are launched */
    wdbCtxStartLibInit ();              /* ability to notify the host when a task starts */
    wdbUserEvtLibInit ();               /* ability to send user events to the host */
    wdbMdlSymSyncLibInit ();            /* Synchronize modules and symbols between the target server and a target */
    usrWdbInitDone ();                  /* The WDB agent is initialized, it then can be used to debug the VxWorks system. */
    usrWdbBanner ();                    /* print banner to console after the agent is initialized */
    }



/******************************************************************************
*
* hardWareInterFaceBusInit - bus-subsystem initialization
*/

void hardWareInterFaceBusInit (void)
    {
    vxbLibInit();                       /* vxBus Library Initialization */
    plbRegister();                      /* Processor Local Bus */
    pciRegister();                      /* Peripheral Component Interconnect Bus */
    feiRegister();                      /* fei vxBus END driver */
    miiBusRegister();                   /* MII bus controller for ethernet transceivers */
    genPhyRegister();                   /* Generic 10/100/1000 ethernet copper PHY driver */
    i8042vxbRegister();                 /* driver for commonly found keyboard controllers */
    m6845vxbRegister();                 /* driver for commonly found VGA adapters */
    ns16550SioRegister();               /* ns16550 SIO support */
    vxbFileNvRamRegister();             /* Driver for file-based non-volatile RAM support */
    vxbI8253TimerDrvRegister();         /* i8253 timer Driver */
    pentiumPciRegister();               /* Pentium PCI host controller */
    }



/******************************************************************************
*
* hardWareInterFaceInit - Hardware Interface Pre-Kernel Initialization
*/

void hardWareInterFaceInit (void)
    {
    hwMemLibInit(); hwMemPoolCreate(&hwMemPool[0], HWMEM_POOL_SIZE); /* Init pre-kernel memory allocation globally */
                                        /* Pre-Kernel Memory Allocation */
    usrVxbTimerSysInit();               /* vxBus Timer Support */
    hardWareInterFaceBusInit();         /* vxBus subsystem */
    vxbInit();                          /* vxBus Library Activation */
    vxbSysClkLibInit();                 /* vxBus Sys Clk Support */
    vxbDelayLibInit();                  /* vxBus Delay Timer Support */
    }



/******************************************************************************
*
* vxbDevInit - Device initialization post kernel
*/

STATUS vxbDevInit (void)
    {
    return(vxbDevInitInternal ());      /* vxbus device initialization */
    }



/******************************************************************************
*
* vxbDevConnect - vxBus Device Connect post kernel
*/

STATUS vxbDevConnect (void)
    {
    return (vxbDevConnectInternal ());  /* vxbus device connection */
    }

