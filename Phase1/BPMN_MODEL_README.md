# BPMN Language Model Training Notebook

## 📚 Overview

This Jupyter notebook trains a small language model specialized in BPMN (Business Process Model and Notation) knowledge using the official OMG BPMN 2.0 specification data.

## 🎯 What Does This Notebook Do?

1. **Loads BPMN Training Data**: 1,500+ examples from the official BPMN specification
2. **Fine-tunes DistilGPT-2**: A small, efficient language model (82M parameters)
3. **Creates a BPMN Expert**: Model learns to answer BPMN-related questions
4. **Provides Interactive Testing**: Query the model with your own BPMN questions

## 🚀 Quick Start

### Prerequisites

```bash
pip install transformers datasets torch accelerate tqdm pandas
```

### Running the Notebook

1. **Run all cells in order** (or use "Run All")
2. **Training time**: ~15-30 minutes on CPU, ~5-10 minutes on GPU
3. **Memory**: Requires ~2-4 GB RAM

### Skip Training (Load Pre-trained Model)

If you've already trained the model:
- Jump to the "Quick Start: Load Pre-trained Model" section
- Uncomment and run that cell
- Skip directly to testing!

## 📊 Model Details

### Base Model
- **DistilGPT-2** (82M parameters)
- Lightweight, fast, and free
- Distilled version of GPT-2
- Perfect for domain-specific tasks

### Training Data
- **Source**: Official OMG BPMN 2.0 Specification (via bpmn-io GitHub)
- **Elements**: 322 BPMN elements
- **Q&A Pairs**: 1,318 question-answer examples
- **Comparisons**: 620 element comparison pairs
- **Natural Language**: 322 descriptive texts

### Training Configuration
- **Epochs**: 3
- **Batch Size**: 4 (with gradient accumulation)
- **Learning Rate**: 5e-5
- **Optimizer**: AdamW with weight decay
- **Max Length**: 512 tokens

## 🎓 What the Model Learns

The model is trained to answer questions about:

### Events
- Start Events (None, Message, Timer, Signal, etc.)
- End Events (None, Message, Error, Terminate, etc.)
- Intermediate Events (Catch/Throw)
- Boundary Events

### Tasks & Activities
- User Tasks, Service Tasks
- Script Tasks, Manual Tasks
- Business Rule Tasks
- Send/Receive Tasks
- Subprocesses

### Gateways
- Exclusive Gateway (XOR)
- Parallel Gateway (AND)
- Inclusive Gateway (OR)
- Event-Based Gateway
- Complex Gateway

### Other Elements
- Sequence Flow, Message Flow
- Pools, Lanes
- Data Objects, Data Stores
- Annotations, Associations

## 💡 Example Usage

After training, you can ask questions like:

```python
ask_bpmn_question("What is a StartEvent in BPMN?")
ask_bpmn_question("When should I use a UserTask?")
ask_bpmn_question("What's the difference between ExclusiveGateway and ParallelGateway?")
ask_bpmn_question("What can a MessageFlow connect to?")
```

## 📁 Output Files

After training, you'll find:

```
bpmn_language_model/
├── checkpoint-XXX/          # Training checkpoints
└── logs/                    # Training logs

bpmn_model_final/           # Final saved model
├── config.json
├── pytorch_model.bin
├── tokenizer_config.json
├── vocab.json
└── merges.txt
```

## 🔧 Customization Options

### Change Model Size
```python
# Try different models (larger = better but slower)
model_name = "gpt2"              # 124M params
model_name = "gpt2-medium"       # 355M params
model_name = "gpt2-large"        # 774M params
```

### Adjust Training
```python
# Modify training_args for different behavior
num_train_epochs=5               # More epochs
per_device_train_batch_size=8    # Larger batches (needs more memory)
learning_rate=3e-5               # Different learning rate
```

### Use More Data
```python
# Load all examples instead of subset
for qa in tqdm(qa_pairs):        # Remove [:1000] limit
    formatted = format_instruction(qa)
```

## 📈 Performance Expectations

### Training Results
- **Training Loss**: Should decrease from ~3.5 to ~2.0
- **Validation Loss**: Around 2.0-2.5
- **Convergence**: Typically 2-3 epochs

### Model Capabilities
✅ **Good at**:
- Defining BPMN elements
- Explaining element purposes
- Listing element attributes
- Describing connection rules
- Explaining common patterns

⚠️ **Limitations**:
- May not handle very complex multi-step reasoning
- Limited to knowledge in training data
- Better with factual questions than creative tasks

## 🛠️ Troubleshooting

### Out of Memory Error
```python
# Reduce batch size
per_device_train_batch_size=2
# Or use gradient accumulation
gradient_accumulation_steps=4
```

### Slow Training
```python
# Reduce training data
qa_pairs[:500]  # Use fewer examples
# Or reduce epochs
num_train_epochs=2
```

### Poor Results
```python
# Try more epochs
num_train_epochs=5
# Or adjust learning rate
learning_rate=3e-5
# Or use more training data
```

## 🎯 Next Steps

1. **Test Thoroughly**: Try many BPMN questions to evaluate quality
2. **Expand Data**: Add more training examples for better coverage
3. **Deploy**: Create a web API or chatbot interface
4. **Integrate**: Connect to BPMN modeling tools
5. **Experiment**: Try larger models or different architectures

## 📚 Additional Resources

- **BPMN Specification**: https://www.omg.org/spec/BPMN/
- **Transformers Library**: https://huggingface.co/docs/transformers
- **DistilGPT-2**: https://huggingface.co/distilgpt2
- **BPMN Training Data**: See `Data/bpmn_training_data/` folder

## 📝 Notes

- Model is trained on BPMN 2.0 specification
- All data is from official OMG sources (via bpmn-io)
- Model can be used commercially (MIT/Apache licenses)
- Training is reproducible (seed=42)

## 🤝 Contributing

To improve the model:
1. Add more training examples to the dataset
2. Experiment with different model architectures
3. Fine-tune hyperparameters
4. Add domain-specific tokens to vocabulary

---

**Happy Training! 🎉**

For questions or issues, refer to the BPMN specification or Transformers documentation.
