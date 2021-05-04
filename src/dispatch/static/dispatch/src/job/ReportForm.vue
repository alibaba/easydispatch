<template>
  <v-app>
    <v-content>
      <v-card flat>
        <v-toolbar color="red darken-2" dark extended flat height="150" />

        <v-card class="mx-auto" max-width="600" style="margin-top: -64px;">
          <v-card-text v-if="id">
            <div>Dispatch</div>
            <p class="display-2 text--primary">Security Job Report</p>
            <p>
              This page will be populated with job resources as they are
              created. If you have any questions, please feel free to review the
              Frequently Asked Questions (FAQ) document linked below, and/or
              reach out to the listed Job Commander.
            </p>
            <v-list three-line>
              <v-list-group :value="true">
                <template v-slot:activator>
                  <v-list-item-title class="title"
                    >Job Details</v-list-item-title
                  >
                </template>
                <v-list-item-group>
                  <v-list-item
                    :href="commander.weblink"
                    target="_blank"
                    title="The Job Commander maintains all necessary context, and drives the job to resolution."
                  >
                    <v-list-item-content>
                      <v-list-item-title>Commander</v-list-item-title>
                      <v-list-item-subtitle>{{
                        commander.name
                      }}</v-list-item-subtitle>
                    </v-list-item-content>
                    <v-list-item-action>
                      <v-list-item-icon>
                        <v-icon>open_in_new</v-icon>
                      </v-list-item-icon>
                    </v-list-item-action>
                  </v-list-item>
                  <v-divider />
                  <v-list-item disabled>
                    <v-list-item-content>
                      <v-list-item-title>Title</v-list-item-title>
                      <v-list-item-subtitle>{{ title }}</v-list-item-subtitle>
                    </v-list-item-content>
                  </v-list-item>
                  <v-divider />
                  <v-list-item disabled>
                    <v-list-item-content>
                      <v-list-item-title>Description</v-list-item-title>
                      <v-list-item-subtitle>{{
                        description
                      }}</v-list-item-subtitle>
                    </v-list-item-content>
                  </v-list-item>
                  <v-divider />
                </v-list-item-group>
              </v-list-group>
            </v-list>
            <v-list three-line>
              <v-list-group>
                <template v-slot:activator>
                  <v-list-item-title class="title"
                    >Job Resources</v-list-item-title
                  >
                </template>
                <v-list-item
                  v-if="ticket"
                  :href="ticket.weblink"
                  target="_blank"
                >
                  <v-list-item-content>
                    <v-list-item-title>Ticket</v-list-item-title>
                    <v-list-item-subtitle>{{
                      ticket.description
                    }}</v-list-item-subtitle>
                  </v-list-item-content>
                  <v-list-item-action>
                    <v-list-item-icon>
                      <v-icon>open_in_new</v-icon>
                    </v-list-item-icon>
                  </v-list-item-action>
                </v-list-item>
                <v-list-item v-else>
                  <v-list-item-content>
                    <v-list-item-title>Ticket</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-progress-circular indeterminate color="primary" />
                    </v-list-item-subtitle>
                  </v-list-item-content>
                </v-list-item>
                <v-divider />
                <v-list-item
                  v-if="conference"
                  :href="conference.weblink"
                  target="_blank"
                >
                  <v-list-item-content>
                    <v-list-item-title>Video Conference</v-list-item-title>
                    <v-list-item-subtitle>{{
                      conference.description
                    }}</v-list-item-subtitle>
                  </v-list-item-content>
                  <v-list-item-action>
                    <v-list-item-icon>
                      <v-icon>open_in_new</v-icon>
                    </v-list-item-icon>
                  </v-list-item-action>
                </v-list-item>
                <v-list-item v-else>
                  <v-list-item-content>
                    <v-list-item-title>Video Conference</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-progress-circular indeterminate color="primary" />
                    </v-list-item-subtitle>
                  </v-list-item-content>
                </v-list-item>
                <v-divider />
                <v-list-item
                  v-if="conversation"
                  :href="conversation.weblink"
                  target="_blank"
                >
                  <v-list-item-content>
                    <v-list-item-title>Conversation</v-list-item-title>
                    <v-list-item-subtitle>{{
                      conversation.description
                    }}</v-list-item-subtitle>
                  </v-list-item-content>
                  <v-list-item-action>
                    <v-list-item-icon>
                      <v-icon>open_in_new</v-icon>
                    </v-list-item-icon>
                  </v-list-item-action>
                </v-list-item>
                <v-list-item v-else>
                  <v-list-item-content>
                    <v-list-item-title>Conversation</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-progress-circular indeterminate color="primary" />
                    </v-list-item-subtitle>
                  </v-list-item-content>
                </v-list-item>
                <v-divider />
                <v-list-item
                  v-if="storage"
                  :href="storage.weblink"
                  target="_blank"
                >
                  <v-list-item-content>
                    <v-list-item-title>Storage</v-list-item-title>
                    <v-list-item-subtitle>{{
                      storage.description
                    }}</v-list-item-subtitle>
                  </v-list-item-content>
                  <v-list-item-action>
                    <v-list-item-icon>
                      <v-icon>open_in_new</v-icon>
                    </v-list-item-icon>
                  </v-list-item-action>
                </v-list-item>
                <v-list-item v-else>
                  <v-list-item-content>
                    <v-list-item-title>Storage</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-progress-circular indeterminate color="primary" />
                    </v-list-item-subtitle>
                  </v-list-item-content>
                </v-list-item>
                <v-divider />
                <div v-if="documents">
                  <span
                    v-for="document in documents"
                    :key="document.resource_id"
                  >
                    <v-list-item :href="document.weblink" target="_blank">
                      <v-list-item-content>
                        <v-list-item-title>{{
                          document.resource_type | deslug
                        }}</v-list-item-title>
                        <v-list-item-subtitle>{{
                          document.description
                        }}</v-list-item-subtitle>
                      </v-list-item-content>
                      <v-list-item-action>
                        <v-list-item-icon>
                          <v-icon>open_in_new</v-icon>
                        </v-list-item-icon>
                      </v-list-item-action>
                    </v-list-item>
                    <v-divider />
                  </span>
                </div>
                <span v-else>
                  <v-list-item>
                    <v-list-item-content>
                      <v-list-item-title>Documents</v-list-item-title>
                      <v-list-item-subtitle>
                        <v-progress-circular indeterminate color="primary" />
                      </v-list-item-subtitle>
                    </v-list-item-content>
                  </v-list-item>
                  <v-divider />
                </span>
              </v-list-group>
            </v-list>
            <v-container grid-list-md>
              <v-flex xs12>
                <v-btn color="primary" depressed @click="resetSelected()"
                  >Report another job</v-btn
                >
              </v-flex>
            </v-container>
          </v-card-text>
          <ValidationObserver ref="obs">
            <v-card-text v-if="!id" slot-scope="{ invalid, validated }">
              <div>Dispatch</div>
              <p class="display-1 text--primary">Security Job Report</p>
              <p>
                If you suspect a security job and require help from security,
                please fill out the following to the best of your abilities.
              </p>
              <v-form>
                <v-container grid-list-md>
                  <v-layout wrap>
                    <v-flex xs12>
                      <ValidationProvider
                        name="Title"
                        rules="required"
                        immediate
                      >
                        <v-textarea
                          v-model="title"
                          slot-scope="{ errors, valid }"
                          :error-messages="errors"
                          :success="valid"
                          label="Title"
                          hint="A brief explanatory title. You can change this later."
                          clearable
                          auto-grow
                          rows="2"
                          required
                        />
                      </ValidationProvider>
                    </v-flex>
                    <v-flex xs12>
                      <ValidationProvider
                        name="Description"
                        rules="required"
                        immediate
                      >
                        <v-textarea
                          v-model="description"
                          slot-scope="{ errors, valid }"
                          :error-messages="errors"
                          :success="valid"
                          label="Description"
                          hint="A summary of what you know so far. It's all right if this is incomplete."
                          clearable
                          auto-grow
                          rows="3"
                          required
                        />
                      </ValidationProvider>
                    </v-flex>
                    <v-flex xs12>
                      <tag-filter-combobox
                        v-model="tags"
                        label="Tags"
                      ></tag-filter-combobox>
                    </v-flex>
                  </v-layout>
                  <v-btn
                    color="primary"
                    depressed
                    :loading="loading"
                    :disabled="invalid || !validated"
                    @click="save()"
                    >Submit</v-btn
                  >
                </v-container>
              </v-form>
            </v-card-text>
          </ValidationObserver>
        </v-card>
      </v-card>
    </v-content>
    <!-- App Footer -->
    <v-footer height="auto" class="pa-3 app--footer">
      <span class="caption"
        >Kandbox Planner &copy; {{ new Date().getFullYear() }}</span
      >
      <v-spacer />
      <span class="caption mr-1">Dispatching by AI</span>
      <v-icon color="pink" small>favorite</v-icon>
    </v-footer>
  </v-app>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import TagFilterCombobox from "@/tag/TagFilterCombobox.vue";

extend("required", {
  ...required,
  message: "This field is required"
});

// import JobMembersCombobox from "@/job/JobMembersCombobox.vue"
export default {
  name: "ReportForm",

  components: {
    ValidationProvider,
    ValidationObserver,
    TagFilterCombobox
  },
  data() {
    return {
      isSubmitted: false
    };
  },
  computed: {
    ...mapFields("job", [
      "selected.commander",
      "selected.job_code",
      "selected.tags",
      "selected.description",
      "selected.conversation",
      "selected.conference",
      "selected.storage",
      "selected.documents",
      "selected.loading",
      "selected.ticket",
      "selected.id"
    ])
  },

  methods: {
    ...mapActions("job", ["save", "get", "resetSelected"])
  }
};
</script>
