#ifndef _AVMRUNTIME_H
#define _AVMRUNTIME_H

#ifdef __cplusplus
extern "C" {
#endif

  struct codeblock;
  struct context;

  typedef void *(*codeblock_fn_t)(struct context *);
  typedef codeblock_fn_t(*codeblock_compiler_t)(void);

  typedef struct codeblock
  {
    codeblock_fn_t compiled;
    codeblock_compiler_t compiler;
  } codeblock_t;

  typedef struct context
  {
    const char *buffer;
    long len;
    long index;
    void *matchval;
    unsigned long *tagmatrix;
  } context_t;

  extern codeblock_t *codeblock_factory(void);

#ifdef __cplusplus
}
#endif

#endif
