#ifndef DLFCN_H
#define DLFCN_H

#define RTLD_NOW 2

int dlclose(void *handle);
char *dlerror(void);
void *dlopen(const char *filename, int flag);
void *dlsym(void *handle, const char *symbol);

#endif /* DLFCN_H */
