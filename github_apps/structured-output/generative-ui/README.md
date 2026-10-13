# Generative UI with Structured Outputs

## Overview

This simple demo app showcases how to generate UI dynamically based on a user input, using Structured Outputs to reliably generate components that will be rendered recursively.

![Generative UI Demo](./public/screenshot.jpg)

## Features

- Multi-turn conversation handling
- Automatic tool execution
- Streaming responses and function calls
- Streaming generative UI

## How to run

1. Clone the repository:

   ```bash
   git clone https://github.com/openai/structured-outputs-samples.git
   cd generative-ui
   ```

2. Install dependencies:

   ```bash
   npm i
   ```

3. Set up your environment:

   ```bash
   export OPENAI_API_KEY=your-api-key
   ```

   Or create a `.env` file in the `generative-ui` folder containing:

   ```bash
   OPENAI_API_KEY=<your-api-key>
   ```

4. Run the demo

   ```bash
   npm run dev
   ```

   The app will be available at [`http://localhost:3000`](http://localhost:3000).

## Usage

To try this demo, ask questions that can be represented visually.
You can try the suggested prompts or ask something else.

To see the arguments for the `generate_ui` tool, you can toggle the JSON view by clicking on the curly braces icon in the top right corner of the UI display.

## Customization

This demo app can be easily customized by modifying the components and their parameters used by the `generate_ui` tool.

Update the `components-definition.ts` file to add or remove components, and make sure you update the `components.tsx` file so that each component definition maps to a React component.
