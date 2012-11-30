#include <stdio.h>
#include <stdlib.h>
#include "avmruntime.h"

#define INLINE inline
#define API extern INLINE

static INLINE void prepare(codeblock_t *cb)
{
  if(!cb->compiled)
  {
    cb->compiled = cb->compiler();
  }
}

/* returns 1 if the consume was successful and 0 if not, code generation should return on 0 */
API int consume(context_t *ctx)
{
  if(ctx->index >= ctx->len - 1)
    return 0;

  ctx->matchval = NULL;
  ctx->index++;
  return 1;
}

API codeblock_t *select_op(context_t *ctx, codeblock_t **table)
{
  return table[*(ctx->buffer + ctx->index)];
}

API  int compare(context_t *ctx, char c)
{
  return c == *(ctx->buffer + ctx->index);
}

API  void match(context_t *ctx, void *rv)
{
  ctx->matchval = rv;
}

/* should be followed by a return in code generation */
API  void * leave(context_t *ctx)
{
  return ctx->matchval;
}

/* execute arbitrary code */
API  void exec(context_t *ctx, void(*code)(void))
{
  code();
}

/* 
 * branching calls should all be followed by a return of the result in code generation 
 */
API void * branch(context_t *ctx, codeblock_t *cb)
{
  prepare(cb);
  return cb->compiled(ctx);
}

/*
 * tag handling instructions
 */
API void ltagv_op(context_t *ctx, unsigned long tag, unsigned long src, unsigned long dst)
{
  ctx->tagmatrix[tag,dst] = ctx->tagmatrix[tag,src];
}

API void utagv_op(context_t *ctx, unsigned long tag, unsigned long dst)
{
  ctx->tagmatrix[tag,dst] = ctx->index;
}
