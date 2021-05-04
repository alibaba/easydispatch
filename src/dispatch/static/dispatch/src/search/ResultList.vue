<template>
  <v-card class="mx-auto">
    <v-subheader>Search results for: "{{ query }}"</v-subheader>
    <v-list v-if="!results.length">
      <v-list-item no-action>
        <v-list-item-content>
          <v-list-item-title class="title"
            >Sorry, we didn't find anything matching your
            query.</v-list-item-title
          >
        </v-list-item-content>
      </v-list-item>
    </v-list>
    <div v-else>
      <job-list :items="jobs" />
      <tag-list :items="tags" />
      <worker-list :items="workers" />
      <team-list :items="teams" />
      <service-list :items="services" />
    </div>
  </v-card>
</template>

<script>
import { mapState } from "vuex";
import JobList from "@/job/List.vue";
import ServiceList from "@/service/List.vue";
import WorkerList from "@/worker/List.vue";
import TeamList from "@/team/List.vue";
import TagList from "@/tag/List.vue";
export default {
  name: "SearchResultList",
  components: {
    JobList,
    ServiceList,
    WorkerList,
    TeamList,
    TagList
  },
  data() {
    return {};
  },

  computed: {
    ...mapState("search", ["results", "query"]),
    definitions() {
      return this.results.filter(item => {
        return item.type.toLowerCase().includes("definition");
      });
    },
    services() {
      return this.results.filter(item => {
        return item.type.toLowerCase().includes("service");
      });
    },
    workers() {
      return this.results.filter(item => {
        return item.type.toLowerCase().includes("worker");
      });
    },
    teams() {
      return this.results.filter(item => {
        return item.type.toLowerCase().includes("team");
      });
    },
    terms() {
      return this.results.filter(item => {
        return item.type.toLowerCase().includes("term");
      });
    },
    tags() {
      return this.results.filter(item => {
        return item.type.toLowerCase().includes("tag");
      });
    },
    tasks() {
      return this.results.filter(item => {
        return item.type.toLowerCase().includes("task");
      });
    },
    jobs() {
      return this.results.filter(item => {
        return item.type.toLowerCase().includes("job");
      });
    }
  },

  methods: {}
};
</script>
