/* Completed save preservation, bounded retention, and failure-before-prune. */
#include "../src/autosave_history.h"
#include <assert.h>
#include <errno.h>
#include <unistd.h>
#ifdef _WIN32
#include <direct.h>
#define MKDIR(p) _mkdir(p)
#else
#define MKDIR(p) mkdir(p,0700)
#endif
static int dirs(const char *p){return MKDIR(p)&&errno!=EEXIST?-1:0;}
static void remove_dir(const char *p){
    const char *files[]={"dis.dat","param.bin","icon0.png","slot.txt"};char path[1200];
    for(int i=0;i<4;++i){snprintf(path,sizeof(path),"%s/%s",p,files[i]);remove(path);}rmdir(p);
}
static void bytes(const char *p,int n,int v){FILE*f=fopen(p,"wb");assert(f);while(n--)assert(fputc(v,f)!=EOF);assert(!fclose(f));}
int main(int argc,char **argv){
    assert(argc==2);char host[1024],meta[1024],history[1024],data[1200],param[1200];
    snprintf(host,sizeof(host),"%s/slot",argv[1]);snprintf(meta,sizeof(meta),"%s/meta",argv[1]);snprintf(history,sizeof(history),"%s/history",argv[1]);
    assert(!dirs(host)&&!dirs(meta));snprintf(data,sizeof(data),"%s/dis.dat",host);snprintf(param,sizeof(param),"%s/param.bin",meta);
    bytes(param,1328,7);bytes(data,131072,1);
    assert(iss_history_capture(history,"infamousssUser0",host,meta,dirs,remove_dir)==0);
    struct stat st;assert(stat(history,&st));
    assert(iss_history_capture(history,"infamousssAuto0",host,meta,dirs,remove_dir)==1);
    assert(iss_history_capture(history,"infamousssAuto1",host,meta,dirs,remove_dir)==0);
    for(int i=2;i<=7;++i){bytes(data,131072,i);assert(iss_history_capture(history,i%2?"infamousssAuto1":"infamousssAuto0",host,meta,dirs,remove_dir)==1);}
    DIR*d=opendir(history);assert(d);struct dirent*e;int count=0;while((e=readdir(d)))if(iss_history_id(e->d_name))++count;closedir(d);assert(count==5);
    char first[1200],latest[1200];snprintf(first,sizeof(first),"%s/entry-%020d",history,1);assert(stat(first,&st));
    snprintf(latest,sizeof(latest),"%s/entry-%020d/dis.dat",history,7);assert(iss_history_equal(data,latest));
    bytes(data,131072,8);bytes(param,1,1);
    assert(iss_history_capture(history,"infamousssAuto0",host,meta,dirs,remove_dir)==-1);
    assert(!stat(latest,&st));snprintf(first,sizeof(first),"%s/entry-%020d",history,3);assert(!stat(first,&st));
    bytes(data,4,9);assert(iss_history_capture(history,"infamousssAuto0",host,meta,dirs,remove_dir)==-1);
    puts("PASS: five immutable autosaves, both rotating slots, dedup, manual exclusion, failed copies do not prune");
}
