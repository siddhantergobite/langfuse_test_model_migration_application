import { FAQExtract } from "@/stores/useDataStore";
import { Action } from "@/stores/useConversationStore";

export const AGENT_NAME = "Blossom";

export const CUSTOMER_DETAILS = {
  name: "Janet Deer",
  id: "cus_28X44",
  orderNb: 10,
  signupDate: "2023-11-28",
};

export const DEFAULT_ACTION: Action = {
  name: "create_ticket",
  parameters: {
    user_id: CUSTOMER_DETAILS.id,
    type: "other",
    details: "Need more help with the request",
  },
};

export const DEFAULT_ARTICLES: FAQExtract[] = [
  {
    title: "Interactions guidelines",
    content: `Tone, Empathy, and Professionalism:
      As a representative, you are the voice of our brand. Always:
      - Be polite, patient, and empathetic.
      - Assume the customer's intent is positive, even if they express frustration.
      - Acknowledge and validate their concerns before providing solutions.
      `,
    link: "/kb?section=interactions_guidelines",
    type: "knowledge_base",
    score: 0.9,
  },
  {
    title: "Customer support chat",
    content: `If you have any questions or need any help, you can contact us through the customer support chat.
    A customer support representative will help you with your questions or concerns.
    Please note that our agents are available from Monday to Saturday, 9am to 6pm.
    `,
    link: "/faq?section=help_chat",
    type: "faq",
    score: 0.8,
  },
];

export const KB_FOLDERS = ["knowledge_base", "faq"];
