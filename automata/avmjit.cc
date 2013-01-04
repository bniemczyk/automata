#include <stdlib.h>
#include <stdio.h>

#include <iostream>
#include <string>
#include <memory>

#include "avmruntime.h"

#include <llvm/LLVMContext.h>
#include <llvm/Module.h>
#include <llvm/IRBuilder.h>
#include <llvm/Constants.h>
#include <llvm/Instruction.h>
#include <llvm/Intrinsics.h>
#include <llvm/GlobalVariable.h>
#include <llvm/ExecutionEngine/ExecutionEngine.h>
#include <llvm/ExecutionEngine/GenericValue.h>
#include <llvm/ExecutionEngine/JIT.h>
#include <llvm/Support/TargetSelect.h>
#include <llvm/PassManager.h>
#include <llvm/LinkAllPasses.h>
#include <llvm/TypeBuilder.h>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Support/system_error.h>
#include <llvm/Linker.h>
#include <llvm/ADT/OwningPtr.h>
#include <llvm/Bitcode/ReaderWriter.h>
#include <llvm/Transforms/IPO/PassManagerBuilder.h>
#include <llvm/PassRegistry.h>
#include <llvm/Transforms/Utils/Cloning.h>
#include <llvm/Function.h>

#ifdef PROFILE
#include <google/profiler.h>
#else
#define ProfilerStart(x)
#define ProfilerStop()
#endif


#define API extern "C"
#define INTERNAL

class StateBuilder;

static bool initialized = false;

class VM
{
  public:
    llvm::LLVMContext context;
    llvm::Module *mod;
    llvm::ExecutionEngine *ee;

    llvm::Function *consume_op;
    llvm::Function *compare_op;
    llvm::Function *match_op;
    llvm::Function *leave_op;
    llvm::Function *exec_op;
    llvm::Function *branch_op;
    llvm::Function *cbranch_op;
    llvm::Function *select_op;
    llvm::Function *ltagv_op;
    llvm::Function *utagv_op;

    llvm::Type * codeblock_type;
    llvm::FunctionType * statefn_type;
    std::vector<codeblock_t *> *codeblocks;

    inline VM(const char *runtime_file)
      : context()
    {
      if(!initialized) 
      {
        initialized = true;
        llvm::llvm_start_multithreaded();
        llvm::InitializeAllTargets();
        llvm::InitializeAllTargetMCs();
        llvm::InitializeAllAsmPrinters();
        llvm::initializeAnalysis(*llvm::PassRegistry::getPassRegistry());
      }
      //llvm::initializeCore(NULL);
      //this->mod = new llvm::Module("", this->context);

      llvm::OwningPtr<llvm::MemoryBuffer> mbptr;
      llvm::MemoryBuffer::getFile(runtime_file, mbptr);
      if(!mbptr.get())
      {
        std::cerr << "could not load runtime " << runtime_file << "\n";
        std::cerr << "membuf: " << mbptr.get() << "\n";
        return;
      }

      //std::cerr << "mbuf: " << mbptr->getBufferStart() << "\n";
      //std::string *errorMsg = new std::string("ERROR GENERIC");
      //llvm::StringRef errorMsg;
      std::string errorMsg("GENERIC ERROR");
      llvm::Module *lib = llvm::ParseBitcodeFile(mbptr.get(), this->context, &errorMsg);
      lib->MaterializeAll();
      if(!lib) {
        std::cerr << errorMsg << "\n";
        return;
      }

      llvm::Linker linker("ProgramName", lib, 0);
      linker.setFlags(llvm::Linker::Verbose);
      this->mod = linker.releaseModule();
      this->mod->MaterializeAll();

      this->consume_op = this->mod->getFunction("consume");
      this->compare_op = this->mod->getFunction("compare");
      this->match_op = this->mod->getFunction("match");
      this->leave_op = this->mod->getFunction("leave");
      this->exec_op = this->mod->getFunction("exec");
      this->branch_op = this->mod->getFunction("branch");
      this->cbranch_op = this->mod->getFunction("cbranch");
      this->select_op = this->mod->getFunction("select_op");
      this->ltagv_op = this->mod->getFunction("ltagv_op");
      this->utagv_op = this->mod->getFunction("utagv_op");

      llvm::EngineBuilder eb(this->mod);
      eb.setUseMCJIT(true);
      eb.setOptLevel(llvm::CodeGenOpt::Aggressive);
      this->ee = eb.create();
      //this->ee->DisableLazyCompilation();

      this->codeblock_type = this->mod->getTypeByName("struct.codeblock");
      this->statefn_type = this->leave_op->getFunctionType();
      this->codeblocks = new std::vector<codeblock_t *>();
    }

    inline ~VM(void)
    {
      delete this->ee;
      delete this->codeblocks;
    }

    INTERNAL StateBuilder *statebuilder_factory(void);
    INTERNAL void *Run(codeblock_t *, const char *str, unsigned long len, unsigned long state_count, unsigned long tag_count);
    INTERNAL codeblock_t *codeblock_factory(codeblock_compiler_t);
    INTERNAL void replace_compiled_fn(codeblock_fn_t o, codeblock_fn_t n);

};

class StateBuilder
{
  private:
    VM *vm;
    llvm::Function *fn;
    llvm::IRBuilder<> *builder;
    llvm::Value *lastCompare;
    llvm::Value *contextArg;

  public:
    inline StateBuilder(VM *_vm) : vm(_vm) 
  {
    auto fn = this->vm->mod->getOrInsertFunction("", this->vm->statefn_type);
    this->fn = static_cast<llvm::Function *>(fn);
    if(!this->fn) {
      std::cerr << "could not generate a state function\n";
      return;
    }

    llvm::BasicBlock *bb = llvm::BasicBlock::Create(this->vm->context, "", this->fn);
    this->builder = new llvm::IRBuilder<>(bb);
    this->lastCompare = NULL;
    this->contextArg = &this->fn->getArgumentList().front();
  }

    inline ~StateBuilder(void)
    {
      //delete this->builder;
    }

    INTERNAL void Consume(void);
    INTERNAL void Compare(const char);
    INTERNAL void Match(void *);
    INTERNAL void Leave(void);
    INTERNAL void Exec(void(*)(void));
    INTERNAL void Branch(codeblock_t *);
    INTERNAL void CBranch(codeblock_t *onTrue);
    INTERNAL void Switch(unsigned long count, const unsigned char *, codeblock_t **);
    INTERNAL void LTagV(unsigned long tag, unsigned long src, unsigned long dst);
    INTERNAL void UTagV(unsigned long tag, unsigned long dst);

    INTERNAL void * Compile(void);
};

API VM * avm_vm_factory(const char *runtime_file)
{
  return new VM(runtime_file);
}

API void avm_vm_destroy(VM *vm)
{
  delete vm;
}

INTERNAL inline codeblock_t *VM::codeblock_factory(codeblock_compiler_t compiler)
{
  auto rv = new codeblock_t;
  rv->compiler = compiler;
  rv->compiled = NULL;
  this->codeblocks->push_back(rv);
  return rv;
}

INTERNAL inline void VM::replace_compiled_fn(codeblock_fn_t _old, codeblock_fn_t _new)
{
  for(auto i = this->codeblocks->begin(); i <= this->codeblocks->end(); i++)
  {
    if((*i)->compiled == _old)
      (*i)->compiled = _new;
  }
}

API void avm_vm_replace_compiled_fn(VM *vm, codeblock_fn_t _old, codeblock_fn_t _new)
{
  return vm->replace_compiled_fn(_old, _new);
}


API codeblock_t *avm_vm_codeblock_factory(VM *vm, codeblock_compiler_t compiler)
{
  return vm->codeblock_factory(compiler);
}

INTERNAL inline StateBuilder *VM::statebuilder_factory(void)
{
  return new StateBuilder(this);
}

API StateBuilder * avm_vm_statebuilder_factory(VM *vm)
{
  return vm->statebuilder_factory();
}

INTERNAL inline void * VM::Run(codeblock_t *cb, const char *str, unsigned long len, unsigned long state_count, unsigned long tag_count)
{
  context_t *ctx = new context_t;
  ctx->buffer= str;
  ctx->len = len;
  ctx->index = -1;
  ctx->matchval = NULL;

  if(tag_count != 0)
  {
    ctx->tagmatrix = (unsigned long *)calloc(tag_count * state_count, sizeof(unsigned long));
  } 
  else
  {
    ctx->tagmatrix = NULL;
  }

  if(!cb->compiled)
  {
    cb->compiled = cb->compiler();
  }

  void *rv = cb->compiled(ctx);
  delete ctx;
  return rv;
}

API void * avm_vm_run(VM *vm, codeblock_t *cb, const char *str, unsigned long len, unsigned long state_count, unsigned tag_count)
{
  return vm->Run(cb, str, len, state_count, tag_count);
}

API void avm_statebuilder_destroy(StateBuilder *sb)
{
  delete sb;
}

INTERNAL inline void StateBuilder::Consume(void)
{
  llvm::IRBuilder<> *oldbuilder = this->builder;
  llvm::CallInst *consumed = this->builder->CreateCall(this->vm->consume_op, this->contextArg);
  llvm::Value *notconsumed = this->builder->CreateICmpEQ(consumed, llvm::ConstantInt::get(consumed->getType(), 0));

  llvm::BasicBlock *take = llvm::BasicBlock::Create(this->vm->context, "", this->fn);
  llvm::BasicBlock *notake = llvm::BasicBlock::Create(this->vm->context, "", this->fn);
  llvm::IRBuilder<> *btake = new llvm::IRBuilder<>(take);
  llvm::Value *leave = btake->CreateCall(this->vm->leave_op, this->contextArg);
  btake->CreateRet(leave);

  this->builder = new llvm::IRBuilder<>(notake);
  oldbuilder->CreateCondBr(notconsumed, take, notake);

  delete btake;
}

API void avm_statebuilder_consume(StateBuilder *sb)
{
  sb->Consume();
}

INTERNAL inline void StateBuilder::Compare(const char c)
{
  llvm::APInt apint(sizeof(char) * 8, c, true);
  llvm::ConstantInt *cint = llvm::ConstantInt::get(this->vm->context, apint);
  this->lastCompare = this->builder->CreateCall2(this->vm->compare_op, this->contextArg, cint);
}

API void avm_statebuilder_compare(StateBuilder *sb, const char c)
{
  sb->Compare(c);
}

INTERNAL inline void StateBuilder::Match(void *v)
{
  llvm::APInt apint(sizeof(void *) * 8, (unsigned long)v, true);
  llvm::ConstantInt *con = llvm::ConstantInt::get(this->vm->context, apint);
  llvm::Value *ptr = llvm::ConstantExpr::getIntToPtr(con, this->fn->getReturnType()); 
  this->builder->CreateCall2(this->vm->match_op, this->contextArg, ptr);
}

API void avm_statebuilder_match(StateBuilder *sb, void *v)
{
  sb->Match(v);
}

INTERNAL inline void StateBuilder::Leave(void)
{
  llvm::Value *rv = this->builder->CreateCall(this->vm->leave_op, this->contextArg);
  this->builder->CreateRet(rv);
}

API void avm_statebuilder_leave(StateBuilder *sb)
{
  sb->Leave();
}

INTERNAL inline void StateBuilder::Exec(void(*target)(void))
{
  llvm::APInt apint(sizeof(void(*)(void)) * 8, (unsigned long)target, true);
  llvm::ConstantInt *con = llvm::ConstantInt::get(this->vm->context, apint);
  llvm::ArrayRef<llvm::Type *> ptypes;
  llvm::FunctionType *ftype = llvm::FunctionType::get(llvm::Type::getVoidTy(this->vm->context), ptypes, false);
  llvm::PointerType *ptype = llvm::PointerType::getUnqual(ftype);
  llvm::Value *ptr = llvm::ConstantExpr::getIntToPtr(con, ptype);
  this->builder->CreateCall2(this->vm->exec_op, this->contextArg, ptr);
}

API void avm_statebuilder_execute(StateBuilder *sb, void(*target)(void))
{
  sb->Exec(target);
}

INTERNAL inline void StateBuilder::Branch(codeblock_t *target)
{
  llvm::APInt apint(sizeof(codeblock_t *) * 8, (unsigned long)target, true);
  llvm::ConstantInt *con = llvm::ConstantInt::get(this->vm->context, apint);
  llvm::PointerType *ptrt = llvm::PointerType::getUnqual(this->vm->codeblock_type);
  llvm::Value *ptr = llvm::ConstantExpr::getIntToPtr(con, ptrt);
  llvm::Value *rv = this->builder->CreateCall2(this->vm->branch_op, this->contextArg, ptr);
  this->builder->CreateRet(rv);
}

API void avm_statebuilder_branch(StateBuilder *sb, codeblock_t *target)
{
  sb->Branch(target);
}

INTERNAL inline void StateBuilder::CBranch(codeblock_t *target)
{
  llvm::IRBuilder<> *oldbuilder = this->builder;

  llvm::BasicBlock *take = llvm::BasicBlock::Create(this->vm->context, "", this->fn);
  llvm::BasicBlock *notake = llvm::BasicBlock::Create(this->vm->context, "", this->fn);

  this->builder = new llvm::IRBuilder<>(take);
  this->Branch(target);

  //delete this->builder;
  this->builder = new llvm::IRBuilder<>(notake);

  llvm::Value *castedcmp = oldbuilder->CreateIntCast(
      this->lastCompare, 
      llvm::IntegerType::get(this->vm->context, 1), 
      false);
  oldbuilder->CreateCondBr(castedcmp, take, notake);
  //delete oldbuilder;
}

API void avm_statebuilder_cbranch(StateBuilder *sb, codeblock_t *target)
{
  sb->CBranch(target);
}

INTERNAL inline void StateBuilder::Switch(
    unsigned long count, const unsigned char *constants, codeblock_t **targets)
{
  codeblock_t **table = (codeblock_t **) calloc(256, sizeof(codeblock_t *));
  for(unsigned long i = 0; i < count; i++)
  {
    table[constants[i]] = targets[i];
  }

  auto take = llvm::BasicBlock::Create(this->vm->context, "", this->fn);
  auto notake = llvm::BasicBlock::Create(this->vm->context, "", this->fn);

  // select the correct codeblock
  llvm::APInt aptable(sizeof(void *) * 8, (unsigned long)table, true);
  auto inttable = llvm::ConstantInt::get(this->vm->context, aptable);
  auto ptable = llvm::ConstantExpr::getIntToPtr(inttable, 
      this->vm->select_op->getArgumentList().back().getType());
  auto selected = this->builder->CreateCall2(this->vm->select_op, this->contextArg, ptable);

  // decide if a valid codeblock was returned
  auto iselected = this->builder->CreatePtrToInt(
      selected, 
      llvm::IntegerType::get(this->vm->context, sizeof(codeblock_t **) * 8));

  llvm::APInt nullint(sizeof(void *) * 8, 0, true);
  auto nullselected = this->builder->CreateICmpEQ(
      iselected,
      llvm::ConstantInt::get(this->vm->context, nullint));
  this->builder->CreateCondBr(nullselected, notake, take);

  // gen code if a codeblock was returned
  this->builder = new llvm::IRBuilder<>(take);
  auto rv = this->builder->CreateCall2(this->vm->branch_op, this->contextArg, selected);
  this->builder->CreateRet(rv);

  // continue if a codeblock was not returned
  this->builder = new llvm::IRBuilder<>(notake);
}

API void avm_statebuilder_switch(StateBuilder *sb, 
    unsigned long count, const unsigned char *constants, codeblock_t **targets)
{
  sb->Switch(count, constants, targets);
}

INTERNAL inline void StateBuilder::LTagV(
    unsigned long tag, unsigned long src, unsigned long dst)
{
  llvm::APInt ap_tag(sizeof(unsigned long) * 8, tag, true);
  llvm::APInt ap_src(sizeof(unsigned long) * 8, src, true);
  llvm::APInt ap_dst(sizeof(unsigned long) * 8, dst, true);
  auto c_tag = llvm::ConstantInt::get(this->vm->context, ap_tag);
  auto c_src = llvm::ConstantInt::get(this->vm->context, ap_src);
  auto c_dst = llvm::ConstantInt::get(this->vm->context, ap_dst);

  this->builder->CreateCall4(this->vm->ltagv_op, this->contextArg, c_tag, c_src, c_dst);
}

API void avm_statebuilder_ltagv(StateBuilder *sb, unsigned long tag, unsigned long src, unsigned long dst)
{
  sb->LTagV(tag,src,dst);
}

INTERNAL inline void StateBuilder::UTagV(
    unsigned long tag, unsigned long dst)
{
  llvm::APInt ap_tag(sizeof(unsigned long) * 8, tag, true);
  llvm::APInt ap_dst(sizeof(unsigned long) * 8, dst, true);
  auto c_tag = llvm::ConstantInt::get(this->vm->context, ap_tag);
  auto c_dst = llvm::ConstantInt::get(this->vm->context, ap_dst);

  this->builder->CreateCall3(this->vm->utagv_op, this->contextArg, c_tag, c_dst);
}

API void avm_statebuilder_utagv(StateBuilder *sb, unsigned long tag, unsigned long dst)
{
  sb->UTagV(tag,dst);
}

INTERNAL inline void * StateBuilder::Compile(void)
{
  llvm::FunctionPassManager pm(this->vm->mod);
  llvm::PassManagerBuilder pmb;
  pmb.populateFunctionPassManager(pm);
  //pm.add(dl);
  //pm.add(llvm::createAlwaysInlinerPass());
  pm.add(llvm::createBasicAliasAnalysisPass());
  pm.add(llvm::createInstructionCombiningPass());
  pm.add(llvm::createReassociatePass());
  pm.add(llvm::createGVNPass());
  pm.add(llvm::createTailCallEliminationPass());
  //pm.add(llvm::createPostDomTree());
  pm.doInitialization();
  pm.run(*this->fn);

  //this->fn->dump();
  void *rv = this->vm->ee->getPointerToFunction(this->fn);
  return rv;
}

API void * avm_statebuilder_compile(StateBuilder *sb)
{
  return sb->Compile();
}

API void avm_vm_dump(VM *vm)
{
  vm->mod->dump();
}
