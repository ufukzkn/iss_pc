/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Host-only history; never changes the game's slot names or save bytes. */
#ifndef ISS_AUTOSAVE_HISTORY_H
#define ISS_AUTOSAVE_HISTORY_H
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <dirent.h>
#include <sys/stat.h>
#include <utime.h>

static inline int iss_history_equal(const char *a,const char *b) {
    FILE *x=fopen(a,"rb"),*y=fopen(b,"rb");
    if(!x||!y){if(x)fclose(x);if(y)fclose(y);return 0;}
    unsigned char bx[4096],by[4096];size_t nx,ny;int same=1;
    do {nx=fread(bx,1,sizeof(bx),x);ny=fread(by,1,sizeof(by),y);
        if(nx!=ny||memcmp(bx,by,nx)){same=0;break;}
    } while(nx);
    same=same&&!ferror(x)&&!ferror(y);fclose(x);fclose(y);return same;
}
static inline int iss_history_copy(const char *src,const char *dst,long expected) {
    FILE *in=fopen(src,"rb");if(!in)return -1;
    FILE *out=fopen(dst,"wb");if(!out){fclose(in);return -1;}
    unsigned char buf[8192];size_t n;long total=0;int ok=1;
    while((n=fread(buf,1,sizeof(buf),in))){total+=(long)n;if(fwrite(buf,1,n,out)!=n){ok=0;break;}}
    ok=ok&&!ferror(in)&&(expected<0||total==expected);
    fclose(in);if(fflush(out))ok=0;if(fclose(out))ok=0;
    if(!ok||!iss_history_equal(src,dst))return -1;
    struct stat st;struct utimbuf times;
    if(stat(src,&st))return -1;
    times.actime=st.st_atime;times.modtime=st.st_mtime;
    return utime(dst,&times);
}
static inline unsigned long long iss_history_id(const char *name) {
    if(strlen(name)!=26||strncmp(name,"entry-",6))return 0;
    for(int i=6;i<26;++i)if(name[i]<'0'||name[i]>'9')return 0;
    return strtoull(name+6,NULL,10);
}
/* Called while the save-mount lock is held. Commit a complete snapshot before pruning.
 * Failures preserve the old history and never stop the game's own save. */
static inline int iss_history_capture(const char *root,const char *slot,const char *host,const char *meta,
                                     int (*dirs)(const char *),void (*remove_dir)(const char *)) {
    if(strcmp(slot,"infamousssAuto0")&&strcmp(slot,"infamousssAuto1"))return 0;
    if(dirs(root))return -1;
    DIR *d=opendir(root);if(!d)return -1;
    char src[1024],dst[1024],pending[1024],final[1024];
    snprintf(src,sizeof(src),"%s/dis.dat",host);
    struct stat st;if(stat(src,&st)||st.st_size!=131072){closedir(d);return -1;}
    struct dirent *e;unsigned long long newest=0;int count=0,duplicate=0;
    while((e=readdir(d))){
        unsigned long long id=iss_history_id(e->d_name);if(!id)continue;
        ++count;if(id>newest)newest=id;
        snprintf(dst,sizeof(dst),"%s/%s/dis.dat",root,e->d_name);
        if(iss_history_equal(src,dst))duplicate=1;
    }
    closedir(d);if(duplicate)return 0;
    if(newest==~0ULL)return -1;
    snprintf(pending,sizeof(pending),"%s/.pending-%020llu",root,newest+1);
    snprintf(final,sizeof(final),"%s/entry-%020llu",root,newest+1);
    /* Refuse leftovers rather than merging into an interrupted snapshot. */
    if(!stat(pending,&st)||dirs(pending))return -1;
    snprintf(dst,sizeof(dst),"%s/dis.dat",pending);
    if(iss_history_copy(src,dst,131072))goto failed;
    snprintf(src,sizeof(src),"%s/param.bin",meta);snprintf(dst,sizeof(dst),"%s/param.bin",pending);
    if(iss_history_copy(src,dst,1328))goto failed;
    snprintf(src,sizeof(src),"%s/icon0.png",meta);snprintf(dst,sizeof(dst),"%s/icon0.png",pending);
    if(!stat(src,&st)&&iss_history_copy(src,dst,-1))goto failed;
    snprintf(dst,sizeof(dst),"%s/slot.txt",pending);
    FILE *f=fopen(dst,"wb");if(!f)goto failed;
    int ok=fprintf(f,"%s\n",slot)>0;if(fclose(f))ok=0;if(!ok)goto failed;
    if(rename(pending,final))goto failed;
    ++count;
    while(count>5){
        d=opendir(root);if(!d)return -1;unsigned long long oldest=~0ULL;time_t oldest_time=0;
        while((e=readdir(d))){
            unsigned long long id=iss_history_id(e->d_name);if(!id)continue;
            snprintf(dst,sizeof(dst),"%s/%s/dis.dat",root,e->d_name);
            if(stat(dst,&st)){closedir(d);return -1;}
            if(oldest==~0ULL||st.st_mtime<oldest_time||(st.st_mtime==oldest_time&&id<oldest)){
                oldest=id;oldest_time=st.st_mtime;
            }
        }
        closedir(d);if(oldest==~0ULL)break;
        snprintf(dst,sizeof(dst),"%s/entry-%020llu",root,oldest);remove_dir(dst);
        if(!stat(dst,&st))return -1;--count;
    }
    return 1;
failed:
    remove_dir(pending);return -1;
}
#endif
